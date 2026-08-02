"""Everything identity: password verification, token minting and checking,
and the two dependencies that gate endpoints.

The pattern to narrate: get_current_user answers "who is this?" (401 when it
cannot), require_manager answers "may this role do this?" (403 when not).
401 means your identity failed; 403 means your identity is fine but your
authority is not. Object-level checks (may you touch THIS record) live with
the endpoints, because they need the record.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.audit import write_audit
from app.config import SECRET_KEY, TOKEN_TTL_MINUTES
from app.database import get_db
from app.models import Role, User

# auto_error=False so a missing Authorization header reaches our code instead
# of the framework's default 403. Missing credentials are a 401: the request
# has no identity. 403 is reserved for a known identity with too little
# authority. The WWW-Authenticate header on 401 responses is what the HTTP
# standard requires so a client knows which scheme to present.
bearer_scheme = HTTPBearer(auto_error=False)


def verify_password(plain: str, password_hash: str) -> bool:
    # bcrypt extracts the salt from the stored hash and does the comparison
    # itself. We never handle salts or compare strings by hand.
    return bcrypt.checkpw(plain.encode(), password_hash.encode())


def create_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    # Three claims: sub is who (the user id), iat is issued-at, exp is the
    # expiry that makes a stolen token a temporary problem instead of a
    # permanent one. The role is NOT in the token on purpose: it is read
    # fresh from the database on every request, so a role change takes
    # effect immediately instead of when the token expires.
    payload = {
        "sub": str(user.id),
        "iat": now,
        "exp": now + timedelta(minutes=TOKEN_TTL_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the token to a live user row. Every protected endpoint depends on this."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        # Pinning algorithms on decode matters: without it, a token claiming
        # algorithm "none" or a different scheme could bypass verification.
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_manager(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    if user.role != Role.MANAGER:
        write_audit(db, "access_denied", user_id=user.id, detail="manager-only endpoint")
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager role required")
    return user
