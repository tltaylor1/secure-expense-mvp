"""Create the database and fill it with sample data.

Run: python seed.py
Deletes any existing database first, so it always produces a known state.
Demo accounts share one password, DEMO_PASSWORD from .env; no password is
written in this repository, demo or otherwise.
"""

from datetime import date

import bcrypt

from app.config import DEMO_PASSWORD
from app.database import Base, SessionLocal, engine
from app.models import Category, Expense, ExpenseStatus, Role, User

DEMO_USERS = [
    ("alice@example.com", Role.EMPLOYEE),
    ("bob@example.com", Role.EMPLOYEE),
    ("mona@example.com", Role.MANAGER),
]

CATEGORIES = ["travel", "meals", "equipment", "other"]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def main() -> None:
    # Fail fast, the same rule as the signing secret: a missing password stops
    # the script instead of falling back to a default that would end up shared.
    if not DEMO_PASSWORD:
        raise SystemExit("DEMO_PASSWORD is not set. Add it to .env first.")

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    db = SessionLocal()
    try:
        categories = {name: Category(name=name) for name in CATEGORIES}
        db.add_all(categories.values())

        users = {}
        demo_hash = hash_password(DEMO_PASSWORD)
        for email, role in DEMO_USERS:
            users[email] = User(email=email, password_hash=demo_hash, role=role)
        db.add_all(users.values())
        db.flush()

        db.add_all(
            [
                Expense(
                    user_id=users["alice@example.com"].id,
                    category_id=categories["meals"].id,
                    amount_cents=4250,
                    description="Client lunch",
                    expense_date=date(2026, 7, 20),
                ),
                Expense(
                    user_id=users["alice@example.com"].id,
                    category_id=categories["travel"].id,
                    amount_cents=18900,
                    description="Train to Portland",
                    expense_date=date(2026, 7, 21),
                    status=ExpenseStatus.APPROVED,
                ),
                Expense(
                    user_id=users["bob@example.com"].id,
                    category_id=categories["equipment"].id,
                    amount_cents=7999,
                    description="Mechanical keyboard",
                    expense_date=date(2026, 7, 22),
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    print("Seeded: 3 users, 4 categories, 3 expenses.")


if __name__ == "__main__":
    main()
