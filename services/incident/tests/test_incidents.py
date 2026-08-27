def _create(client, **overrides):
    payload = {
        "title": "auth service returning 500s",
        "service_name": "auth",
        "severity": "critical",
    }
    payload.update(overrides)
    return client.post("/incidents", json=payload)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_create_incident_starts_open_with_a_created_event(client):
    resp = _create(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "open"
    assert body["resolved_at"] is None

    detail = client.get(f"/incidents/{body['id']}").json()
    assert len(detail["events"]) == 1
    assert detail["events"][0]["event_type"] == "created"


def test_get_incident_not_found(client):
    resp = client.get("/incidents/does-not-exist")
    assert resp.status_code == 404


def test_valid_transition_succeeds_and_is_recorded_in_timeline(client):
    incident = _create(client).json()

    resp = client.post(f"/incidents/{incident['id']}/transition", json={"status": "acknowledged"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "acknowledged"

    detail = client.get(f"/incidents/{incident['id']}").json()
    event_types = [e["event_type"] for e in detail["events"]]
    assert event_types == ["created", "status_change"]
    assert "open -> acknowledged" in detail["events"][1]["message"]


def test_invalid_transition_is_rejected(client):
    incident = _create(client).json()
    # open -> mitigated is not an allowed jump per ALLOWED_TRANSITIONS
    resp = client.post(f"/incidents/{incident['id']}/transition", json={"status": "mitigated"})
    assert resp.status_code == 409


def test_transition_to_resolved_sets_resolved_at(client):
    incident = _create(client).json()
    resp = client.post(f"/incidents/{incident['id']}/transition", json={"status": "resolved"})
    assert resp.json()["resolved_at"] is not None


def test_reopening_a_resolved_incident_clears_resolved_at(client):
    incident = _create(client).json()
    client.post(f"/incidents/{incident['id']}/transition", json={"status": "resolved"})
    resp = client.post(f"/incidents/{incident['id']}/transition", json={"status": "investigating"})
    assert resp.status_code == 200
    assert resp.json()["resolved_at"] is None


def test_closed_is_terminal(client):
    incident = _create(client).json()
    client.post(f"/incidents/{incident['id']}/transition", json={"status": "resolved"})
    client.post(f"/incidents/{incident['id']}/transition", json={"status": "closed"})

    resp = client.post(f"/incidents/{incident['id']}/transition", json={"status": "open"})
    assert resp.status_code == 409


def test_add_comment_appears_in_timeline(client):
    incident = _create(client).json()
    resp = client.post(
        f"/incidents/{incident['id']}/comments",
        json={"message": "checked the logs, it's the DB pool"},
    )
    assert resp.status_code == 201

    detail = client.get(f"/incidents/{incident['id']}").json()
    comments = [e for e in detail["events"] if e["event_type"] == "comment"]
    assert len(comments) == 1
    assert "DB pool" in comments[0]["message"]


def test_list_filters_by_status_service_and_severity(client):
    _create(client, service_name="auth", severity="critical")
    _create(client, service_name="gateway", severity="warning", title="gateway latency spike")

    resp = client.get("/incidents", params={"service_name": "auth"})
    assert len(resp.json()) == 1
    assert resp.json()[0]["service_name"] == "auth"

    resp = client.get("/incidents", params={"severity": "warning"})
    assert len(resp.json()) == 1
    assert resp.json()[0]["service_name"] == "gateway"

    resp = client.get("/incidents", params={"status_filter": "open"})
    assert len(resp.json()) == 2


def test_list_incidents_is_paginated(client):
    for i in range(5):
        _create(client, title=f"incident {i}")

    limited = client.get("/incidents", params={"limit": 2})
    assert len(limited.json()) == 2

    over_the_cap = client.get("/incidents", params={"limit": 500})
    assert over_the_cap.status_code == 422

    offset_page = client.get("/incidents", params={"limit": 2, "offset": 2})
    assert len(offset_page.json()) == 2
    assert {i["id"] for i in limited.json()}.isdisjoint({i["id"] for i in offset_page.json()})


def test_create_incident_links_source_alert_id(client):
    resp = _create(client, source_alert_id="alert-abc-123")
    assert resp.json()["source_alert_id"] == "alert-abc-123"


def test_create_incident_emits_audit_event(client, audit_client):
    incident = _create(client).json()

    created = [c for c in audit_client.calls if c["action"] == "incident.created"]
    assert len(created) == 1
    assert created[0]["resource_id"] == incident["id"]
    assert created[0]["after_state"]["title"] == incident["title"]


def test_transition_emits_audit_event_with_before_and_after_status(client, audit_client):
    incident = _create(client).json()
    audit_client.calls.clear()  # only care about the transition event now

    client.post(f"/incidents/{incident['id']}/transition", json={"status": "acknowledged"})

    events = [c for c in audit_client.calls if c["action"] == "incident.status_changed"]
    assert len(events) == 1
    assert events[0]["resource_id"] == incident["id"]
    assert events[0]["before_state"] == {"status": "open"}
    assert events[0]["after_state"] == {"status": "acknowledged"}


def test_invalid_transition_does_not_emit_an_audit_event(client, audit_client):
    incident = _create(client).json()
    audit_client.calls.clear()

    resp = client.post(f"/incidents/{incident['id']}/transition", json={"status": "mitigated"})
    assert resp.status_code == 409  # open -> mitigated is not a valid jump
    assert audit_client.calls == []


def test_comments_do_not_emit_audit_events(client, audit_client):
    incident = _create(client).json()
    audit_client.calls.clear()

    client.post(f"/incidents/{incident['id']}/comments", json={"message": "checking the logs"})
    assert audit_client.calls == []


def test_audit_failure_does_not_break_incident_creation(client, audit_client):
    audit_client.raise_error = True
    resp = _create(client)
    assert resp.status_code == 201


def test_audit_failure_does_not_break_a_transition(client, audit_client):
    incident = _create(client).json()
    audit_client.raise_error = True

    resp = client.post(f"/incidents/{incident['id']}/transition", json={"status": "acknowledged"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "acknowledged"


# --- Readiness vs liveness (Phase 6 follow-up) -----------------------------
#
# /health (liveness) and /health/ready (readiness) are deliberately
# different depths -- see app/main.py's own comments on each. These
# confirm the distinction actually works, not just that both endpoints
# exist.

def test_liveness_check_is_shallow_and_always_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "incident"}


def test_readiness_check_confirms_database_connectivity(client):
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready", "service": "incident"}


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
