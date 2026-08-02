from conftest import DEMO_PW


def test_login_works(client):
    r = client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": DEMO_PW},
    )
    assert r.status_code == 200
    assert r.json()["access_token"]


def test_wrong_password_and_unknown_email_are_indistinguishable(client):
    """User enumeration defense: both failures must look identical."""
    wrong_pw = client.post(
        "/auth/login", json={"email": "alice@example.com", "password": "nope"}
    )
    no_user = client.post(
        "/auth/login", json={"email": "ghost@example.com", "password": "nope"}
    )
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json() == no_user.json()


def test_me_returns_exactly_the_public_fields(client, alice):
    """Output model check: the password hash must be unreachable."""
    body = client.get("/auth/me", headers=alice).json()
    assert set(body.keys()) == {"id", "email", "role"}


def test_garbage_token_rejected(client):
    r = client.get("/auth/me", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401


def test_missing_token_rejected_with_401(client):
    """No credentials means no identity: 401, never the framework default 403."""
    r = client.get("/auth/me")
    assert r.status_code == 401
    assert r.headers["WWW-Authenticate"] == "Bearer"


def test_login_states_its_expiry_contract(client):
    from app.config import TOKEN_TTL_MINUTES

    r = client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": DEMO_PW},
    )
    assert r.json()["expires_in"] == TOKEN_TTL_MINUTES * 60


def test_login_rejects_unknown_fields(client):
    r = client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "x", "role": "manager"},
    )
    assert r.status_code == 422
