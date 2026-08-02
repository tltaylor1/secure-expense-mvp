"""The sensitive-download attack checklist: ownership on upload and download,
content validation by declared type, actual bytes, and size."""

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32

EXPENSE = {
    "category_id": 1,
    "amount_cents": 2500,
    "description": "Team lunch",
    "expense_date": "2026-07-30",
}


def create_expense(client, headers):
    r = client.post("/expenses", json=EXPENSE, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def upload(client, headers, expense_id, name="r.png", data=PNG, ctype="image/png"):
    return client.post(
        f"/expenses/{expense_id}/receipt",
        files={"file": (name, data, ctype)},
        headers=headers,
    )


def test_owner_uploads_then_owner_and_manager_download(client, alice, mona):
    expense = create_expense(client, alice)
    r = upload(client, alice, expense["id"])
    assert r.status_code == 201
    assert r.json()["has_receipt"] is True

    for headers in (alice, mona):
        dl = client.get(f"/expenses/{expense['id']}/receipt", headers=headers)
        assert dl.status_code == 200
        assert dl.content == PNG
        assert dl.headers["content-type"] == "image/png"
        assert dl.headers["x-content-type-options"] == "nosniff"
        # Server-generated download name: no user text in the header.
        assert f"receipt-{expense['id']}.png" in dl.headers["content-disposition"]


def test_non_owner_cannot_download(client, alice, bob):
    """Object-level authorization on the sensitive download, the core check."""
    expense = create_expense(client, alice)
    assert upload(client, alice, expense["id"]).status_code == 201
    r = client.get(f"/expenses/{expense['id']}/receipt", headers=bob)
    assert r.status_code == 403


def test_cannot_upload_to_anothers_expense(client, alice, bob):
    expense = create_expense(client, alice)
    assert upload(client, bob, expense["id"]).status_code == 403


def test_undeclared_type_rejected(client, alice):
    expense = create_expense(client, alice)
    r = upload(client, alice, expense["id"], name="r.txt", data=b"hello", ctype="text/plain")
    assert r.status_code == 415


def test_content_must_match_declared_type(client, alice):
    """A text file claiming to be a PNG fails the magic-byte check."""
    expense = create_expense(client, alice)
    r = upload(client, alice, expense["id"], data=b"not a png at all")
    assert r.status_code == 415


def test_oversize_rejected(client, alice):
    from app.config import MAX_RECEIPT_BYTES

    expense = create_expense(client, alice)
    big = PNG + b"0" * MAX_RECEIPT_BYTES
    assert upload(client, alice, expense["id"], data=big).status_code == 413


def test_second_receipt_rejected(client, alice):
    expense = create_expense(client, alice)
    assert upload(client, alice, expense["id"]).status_code == 201
    assert upload(client, alice, expense["id"]).status_code == 409


def test_download_without_receipt_is_404(client, alice):
    expense = create_expense(client, alice)
    assert client.get(f"/expenses/{expense['id']}/receipt", headers=alice).status_code == 404


def test_receipt_events_reach_the_audit_trail(client, alice, bob):
    from app.database import SessionLocal
    from app.models import AuditLog

    expense = create_expense(client, alice)
    upload(client, alice, expense["id"])
    client.get(f"/expenses/{expense['id']}/receipt", headers=alice)
    client.get(f"/expenses/{expense['id']}/receipt", headers=bob)

    db = SessionLocal()
    try:
        actions = [row.action for row in db.query(AuditLog).all()]
    finally:
        db.close()
    assert "receipt_uploaded" in actions
    assert "receipt_downloaded" in actions
    assert "access_denied" in actions
