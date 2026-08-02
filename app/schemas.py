"""Request and response models.

Input and output are separate classes on purpose: input models list only the
fields a client may set, output models list only the fields a client may see.
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import ExpenseStatus, Role


class LoginRequest(BaseModel):
    # Unknown fields are an error, not ignored: a request trying to smuggle an
    # extra field should fail loudly, which also surfaces honest client bugs.
    model_config = ConfigDict(extra="forbid")

    # Plain bounded string, not a full email validator: the address is only a
    # login identifier here, and skipping the validator keeps a dependency out.
    email: str = Field(min_length=3, max_length=254)
    # Bounded even here: unbounded fields are a resource-consumption surface.
    password: str = Field(min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    # The server states its expiry contract in seconds; the client displays it
    # without ever needing to decode the token.
    expires_in: int


class UserOut(BaseModel):
    id: int
    email: str
    role: Role
    # No password_hash field: what is not listed cannot leak.


class ExpenseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # No user_id and no status: the server takes identity from the token and
    # every new expense starts pending. A client that could set either field
    # could file expenses as someone else or approve its own.
    category_id: int
    amount_cents: int = Field(gt=0, le=1_000_000_00)  # positive, capped at $1M
    description: str = Field(min_length=1, max_length=500)
    expense_date: date


class ExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    category_id: int
    amount_cents: int
    description: str
    expense_date: date
    status: ExpenseStatus
    created_at: datetime
    # Null until decided; then the row itself says who and when.
    decided_by: int | None
    decided_at: datetime | None
    # Whether evidence is attached; storage details stay server-side.
    has_receipt: bool


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
