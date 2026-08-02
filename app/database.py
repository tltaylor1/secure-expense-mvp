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


def check_connection() -> None:
    """Fail at startup, loudly, when the database refuses the connection.

    Without this the app starts, answers its health check, and then returns a
    generic 500 on the first real request, which tells an operator nothing.
    The most common cause is worth naming: PostgreSQL applies POSTGRES_PASSWORD
    only when it first creates its data directory, so changing that value later
    leaves the stored password and the configured one disagreeing.
    """
    from sqlalchemy import text

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        raise RuntimeError(
            "Cannot connect to the database. If POSTGRES_PASSWORD changed after "
            "the first start, the stored password no longer matches it; discard "
            "the database and start again with: docker compose down -v. "
            f"Underlying error: {type(exc).__name__}"
        ) from exc
