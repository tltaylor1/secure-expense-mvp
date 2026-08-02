import json
import logging

from sqlalchemy.orm import Session

from app.models import AuditLog, utc_now

# The table is the record; this stream is the same event in the shape a log
# collector ships. Payloads carry identifiers and short factual detail only,
# never credentials, tokens, or request bodies.
security_log = logging.getLogger("security")


def write_audit(
    db: Session,
    action: str,
    user_id: int | None = None,
    target_id: int | None = None,
    detail: str = "",
) -> None:
    """Record a security-relevant event. Callers must never pass secrets in detail.

    Deliberately does not commit: the caller commits the action and its audit
    row in one transaction, so a state change cannot exist without its trail
    and a trail cannot describe a change that never happened.
    """
    db.add(AuditLog(user_id=user_id, action=action, target_id=target_id, detail=detail))
    security_log.info(
        json.dumps(
            {
                "ts": utc_now().isoformat(),
                "event": action,
                "user_id": user_id,
                "target_id": target_id,
                "detail": detail,
            },
            separators=(",", ":"),
        )
    )
