import os
import secrets

# Point the app at a separate database file and upload directory BEFORE any
# app import reads the variables, so tests can never touch development data.
os.environ["DATABASE_URL"] = "sqlite:///./test_expenses.db"
os.environ["UPLOAD_DIR"] = "./test_uploads"
# The suite generates its own demo password per run. No literal password
# exists anywhere in this repository, not even a test one: a reader should
# never have to decide whether a credential-shaped string matters.
os.environ["DEMO_PASSWORD"] = secrets.token_hex(12)
DEMO_PW = os.environ["DEMO_PASSWORD"]

import pytest
from fastapi.testclient import TestClient

import seed
from app.main import app


@pytest.fixture(scope="session")
def client():
    seed.main()
    with TestClient(app) as c:
        yield c


def login(client, email, password):
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def alice(client):
    return login(client, "alice@example.com", DEMO_PW)


@pytest.fixture(scope="session")
def bob(client):
    return login(client, "bob@example.com", DEMO_PW)


@pytest.fixture(scope="session")
def mona(client):
    return login(client, "mona@example.com", DEMO_PW)
