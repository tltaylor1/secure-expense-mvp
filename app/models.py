"""The four tables. The schema decisions (integer cents, constrained status,
minimized user data, an audit table) are argued in the README's data model
section; this file is where they become structure.
"""

from datetime import date, datetime, timezone
from enum import StrEnum

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Role(StrEnum):
    EMPLOYEE = "employee"
    MANAGER = "manager"


class ExpenseStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class User(Base):
    """Deliberately minimal: email, hash, role. No name, no profile.
    The role column drives every authorization decision in the app."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    # Only ever a bcrypt hash. The plain password exists in memory during
    # login verification and nowhere else.
    password_hash: Mapped[str] = mapped_column(String(128))
    role: Mapped[Role] = mapped_column(Enum(Role))

    # foreign_keys is explicit because expenses carries two links to users:
    # user_id (the owner) and decided_by (the approver). Ownership follows user_id.
    expenses: Mapped[list["Expense"]] = relationship(
        back_populates="owner", foreign_keys="Expense.user_id"
    )


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    # Integer cents: floats corrupt currency (see README, data model decisions).
    amount_cents: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(500))
    # Indexed because the monthly report filters on it.
    expense_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[ExpenseStatus] = mapped_column(
        Enum(ExpenseStatus), default=ExpenseStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    # Attribution lives on the record, not only in the audit log: the row
    # itself answers "who decided this, and when" without a join. Null until
    # a decision is made.
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    owner: Mapped[User] = relationship(back_populates="expenses", foreign_keys=[user_id])
    category: Mapped[Category] = relationship()
    receipt: Mapped["Receipt | None"] = relationship(back_populates="expense")

    @property
    def has_receipt(self) -> bool:
        # Exposed to clients instead of the receipt row itself: the existence
        # of evidence is shareable, its storage details are not.
        return self.receipt is not None


class Receipt(Base):
    """One receipt file per expense. The file lives on disk under a
    server-generated name; the client's filename is stored as display data
    only and never touches a filesystem path."""

    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    expense_id: Mapped[int] = mapped_column(
        ForeignKey("expenses.id"), unique=True, index=True
    )
    stored_name: Mapped[str] = mapped_column(String(64))
    original_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    expense: Mapped[Expense] = relationship(back_populates="receipt")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Nullable: a failed login has no authenticated user to attribute.
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # Action and time are indexed because they are what an investigation
    # filters on: which events, in which window.
    action: Mapped[str] = mapped_column(String(50), index=True)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Short factual context only; never passwords, tokens, or request bodies.
    detail: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
