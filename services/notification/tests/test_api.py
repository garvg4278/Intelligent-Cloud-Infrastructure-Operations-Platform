def test_health(client):
    assert client.get("/health").status_code == 200


def test_create_notification_delivers_and_renders_template(client, webhook_sender):
    resp = client.post(
        "/notifications",
        json={
            "channel": "webhook",
            "target": "https://hooks.example.com/x",
            "subject": "Alert: {{service}}",
            "body": "{{service}} breached {{metric}}",
            "context": {"service": "auth", "metric": "error rate"},
        },
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "sent"
    assert body["subject"] == "Alert: auth"
    assert body["body"] == "auth breached error rate"
    assert webhook_sender.calls == [
        ("https://hooks.example.com/x", "Alert: auth", "auth breached error rate")
    ]


def test_create_notification_without_context_leaves_plain_text_untouched(client, webhook_sender):
    resp = client.post(
        "/notifications",
        json={
            "channel": "webhook", "target": "https://x",
            "subject": "plain", "body": "no placeholders here",
        },
    )
    assert resp.json()["body"] == "no placeholders here"


def test_get_notification_not_found(client):
    assert client.get("/notifications/does-not-exist").status_code == 404


def test_list_filters_by_status_and_channel(client, webhook_sender):
    client.post(
        "/notifications",
        json={"channel": "webhook", "target": "https://x", "subject": "a", "body": "a"},
    )
    webhook_sender.fail_times = 999  # next one will exhaust retries and end up "failed"
    client.post(
        "/notifications",
        json={"channel": "webhook", "target": "https://x", "subject": "b", "body": "b", "max_attempts": 1},
    )

    sent = client.get("/notifications", params={"status_filter": "sent"}).json()
    failed = client.get("/notifications", params={"status_filter": "failed"}).json()
    assert len(sent) == 1
    assert len(failed) == 1
    assert sent[0]["subject"] == "a"
    assert failed[0]["subject"] == "b"


def test_create_notification_rejects_empty_body(client):
    resp = client.post(
        "/notifications", json={"channel": "webhook", "target": "https://x", "subject": "a", "body": ""}
    )
    assert resp.status_code == 422


def test_create_notification_rejects_invalid_channel(client):
    resp = client.post(
        "/notifications",
        json={"channel": "carrier_pigeon", "target": "https://x", "subject": "a", "body": "a"},
    )
    assert resp.status_code == 422


# --- Readiness vs liveness (Phase 6 follow-up) -----------------------------
#
# /health (liveness) and /health/ready (readiness) are deliberately
# different depths -- see app/main.py's own comments on each. These
# confirm the distinction actually works, not just that both endpoints
# exist.

def test_liveness_check_is_shallow_and_always_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "notification"}


def test_readiness_check_confirms_database_connectivity(client):
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready", "service": "notification"}


def test_readiness_check_returns_503_when_database_is_unreachable(client):
    from sqlalchemy.exc import SQLAlchemyError

    from app.database import get_db
    from app.main import app

    class BrokenSession:
        def execute(self, *args, **kwargs):
            raise SQLAlchemyError("simulated database outage")

    def broken_get_db():
        yield BrokenSession()

    original_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = broken_get_db
    try:
        resp = client.get("/health/ready")
        assert resp.status_code == 503
    finally:
        if original_override is not None:
            app.dependency_overrides[get_db] = original_override
        else:
            app.dependency_overrides.pop(get_db, None)
