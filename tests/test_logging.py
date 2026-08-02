"""The structured security log emits the audit event and never a credential."""

import json


def test_failed_login_emits_structured_event_without_password(client, caplog):
    with caplog.at_level("INFO", logger="security"):
        client.post(
            "/auth/login",
            json={"email": "alice@example.com", "password": "wrong-password-xyz"},
        )
    events = [json.loads(r.message) for r in caplog.records if r.name == "security"]
    assert any(e["event"] == "login_failed" for e in events)
    # The password must not appear anywhere in what was logged.
    assert "wrong-password-xyz" not in caplog.text
