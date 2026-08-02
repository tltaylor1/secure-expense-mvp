"""The monthly export: authorization by query, formula injection neutralized,
sensitive read audited. Tests use a far-future month so seeded data and other
tests cannot bleed into the assertions."""

YEAR, MONTH = 2031, 5


def create(client, headers, description, day):
    r = client.post(
        "/expenses",
        json={
            "category_id": 1,
            "amount_cents": 1000,
            "description": description,
            "expense_date": f"{YEAR}-{MONTH:02d}-{day:02d}",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


def report(client, headers):
    return client.get(f"/reports/expenses.csv?year={YEAR}&month={MONTH}", headers=headers)


def test_report_requires_authentication(client):
    assert client.get(f"/reports/expenses.csv?year={YEAR}&month={MONTH}").status_code == 401


def test_employee_report_contains_only_their_rows(client, alice, bob):
    create(client, alice, "Alice May expense", 3)
    create(client, bob, "Bob May expense", 4)
    body = report(client, alice).text
    assert "Alice May expense" in body
    assert "Bob May expense" not in body
    assert "bob@example.com" not in body


def test_manager_report_covers_the_month(client, alice, bob, mona):
    body = report(client, mona).text
    assert "Alice May expense" in body
    assert "Bob May expense" in body


def test_formula_cells_are_neutralized(client, alice, mona):
    create(client, alice, "=SUM(A1:A9)", 5)
    body = report(client, alice).text
    # The cell must arrive apostrophe-prefixed so spreadsheet apps render it
    # as text instead of executing it. csv quoting wraps it in quotes.
    assert "'=SUM(A1:A9)" in body
    assert '"=SUM(A1:A9)' not in body.replace("'=", "")


def test_download_headers_are_server_generated(client, alice):
    r = report(client, alice)
    assert r.headers["content-type"].startswith("text/csv")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert f'filename="expenses-{YEAR}-{MONTH:02d}.csv"' in r.headers["content-disposition"]


def test_month_bounds_validated(client, alice):
    assert client.get("/reports/expenses.csv?year=2031&month=13", headers=alice).status_code == 422
    assert client.get("/reports/expenses.csv?year=1901&month=5", headers=alice).status_code == 422


def test_report_download_is_audited(client, alice):
    from app.database import SessionLocal
    from app.models import AuditLog

    report(client, alice)
    db = SessionLocal()
    try:
        details = [
            row.detail for row in db.query(AuditLog).filter(AuditLog.action == "report_downloaded")
        ]
    finally:
        db.close()
    assert f"{YEAR}-{MONTH:02d}" in details
