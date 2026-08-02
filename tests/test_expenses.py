EXPENSE = {
    "category_id": 1,
    "amount_cents": 1234,
    "description": "Team lunch",
    "expense_date": "2026-07-28",
}


def create(client, headers, **overrides):
    r = client.post("/expenses", json={**EXPENSE, **overrides}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_employee_sees_only_own_expenses(client, alice, bob):
    """Object-level authorization: the core check of the app."""
    create(client, alice)
    for headers, expected_owner in ((alice, 1), (bob, 2)):
        rows = client.get("/expenses", headers=headers).json()
        assert rows, "expected at least one row"
        assert {row["user_id"] for row in rows} == {expected_owner}


def test_client_cannot_set_owner_or_status(client, alice):
    """Mass assignment: smuggled fields must fail loudly, not apply."""
    r = client.post(
        "/expenses",
        json={**EXPENSE, "user_id": 3, "status": "approved"},
        headers=alice,
    )
    assert r.status_code == 422


def test_created_expense_is_owned_by_token_and_pending(client, alice):
    body = create(client, alice)
    assert body["user_id"] == 1
    assert body["status"] == "pending"


def test_employee_cannot_approve(client, alice, bob):
    expense = create(client, alice)
    r = client.post(f"/expenses/{expense['id']}/approve", headers=bob)
    assert r.status_code == 403


def test_manager_cannot_decide_own_expense(client, mona):
    """Separation of duties."""
    expense = create(client, mona)
    r = client.post(f"/expenses/{expense['id']}/approve", headers=mona)
    assert r.status_code == 403


def test_decided_expense_is_immutable(client, alice, mona):
    expense = create(client, alice)
    first = client.post(f"/expenses/{expense['id']}/approve", headers=mona)
    assert first.status_code == 200
    again = client.post(f"/expenses/{expense['id']}/reject", headers=mona)
    assert again.status_code == 409


def test_decision_is_attributed_on_the_record(client, alice, mona):
    """The row answers who decided and when, without an audit log join."""
    expense = create(client, alice)
    assert expense["decided_by"] is None and expense["decided_at"] is None
    decided = client.post(f"/expenses/{expense['id']}/approve", headers=mona).json()
    assert decided["decided_by"] == 3  # mona, the seeded manager
    assert decided["decided_at"] is not None


def test_input_bounds(client, alice):
    for bad in (
        {"amount_cents": -5},
        {"amount_cents": 0},
        {"description": ""},
        {"description": "x" * 501},
        {"category_id": 999},
    ):
        r = client.post("/expenses", json={**EXPENSE, **bad}, headers=alice)
        assert r.status_code in (400, 422), bad


def test_page_size_is_capped(client, alice):
    assert client.get("/expenses?page_size=500", headers=alice).status_code == 422


def test_denials_reach_the_audit_trail(client, bob, mona):
    """Accountability: a refused action still leaves a record."""
    from app.database import SessionLocal
    from app.models import AuditLog

    expense = create(client, mona)
    client.post(f"/expenses/{expense['id']}/approve", headers=bob)
    client.post(f"/expenses/{expense['id']}/approve", headers=mona)

    db = SessionLocal()
    try:
        actions = {row.action for row in db.query(AuditLog).all()}
    finally:
        db.close()
    assert "access_denied" in actions
    assert "self_decision_denied" in actions
