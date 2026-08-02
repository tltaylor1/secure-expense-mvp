"""Startup must fail loudly on a misconfiguration, with the fix in the message."""

import pytest
from sqlalchemy import create_engine

from app import database


def test_unreachable_database_fails_startup_and_names_the_fix(monkeypatch):
    """A refused connection must stop startup with the command that resolves it,
    rather than letting the app serve and return a generic 500 on first use.
    The common cause is a changed POSTGRES_PASSWORD, which PostgreSQL ignores
    after its data directory exists."""
    # An engine pointed at a port nothing listens on.
    monkeypatch.setattr(
        database, "engine", create_engine("postgresql+psycopg://x:x@127.0.0.1:1/x")
    )
    with pytest.raises(RuntimeError) as err:
        database.check_connection()
    assert "docker compose down -v" in str(err.value)
