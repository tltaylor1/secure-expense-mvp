"""Database plumbing: the engine (one per process), the session factory
(one session per request), and the get_db dependency every endpoint uses.

Nothing in the app talks to the database except through a session from here,
which is what makes "all queries are parameterized" a structural fact rather
than a per-endpoint promise.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL

# check_same_thread is a SQLite-only guard that FastAPI's threading model
# manages itself; PostgreSQL connections take no such argument.
connect_args = (
    {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
engine = create_engine(DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
