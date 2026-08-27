def _create_rule(client, **overrides):
    payload = {
        "name": "high error rate",
        "service_name": "auth",
        "metric_query": 'rate(http_requests_total{status=~"5.."}[5m])',
        "comparison": "gt",
        "threshold": 0.05,
        "severity": "critical",
        "webhook_url": "https://hooks.example.com/alerts",
    }
    payload.update(overrides)
    return client.post("/alerts/rules", json=payload)


def test_health(client):
    assert client.get("/health").status_code == 200


def test_create_rule(client):
    resp = _create_rule(client)
    assert resp.status_code == 201
    assert resp.json()["is_active"] is True


def test_evaluate_below_threshold_creates_no_alert(client, metrics_source):
    rule = _create_rule(client).json()
    metrics_source.value = 0.01  # below the 0.05 threshold

    resp = client.post(f"/alerts/rules/{rule['id']}/evaluate")
    assert resp.status_code == 202

    assert client.get("/alerts").json() == []


def test_evaluate_above_threshold_fires_alert_notifies_and_links_incident(
    client, metrics_source, notifier, incident_client
):
    rule = _create_rule(client).json()
    metrics_source.value = 0.42

    client.post(f"/alerts/rules/{rule['id']}/evaluate")

    alerts = client.get("/alerts").json()
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert["status"] == "firing"
    assert alert["observed_value"] == 0.42
    assert alert["incident_id"] == "fake-incident-1"

    assert len(notifier.sent) == 1
    webhook_url, payload = notifier.sent[0]
    assert webhook_url == "https://hooks.example.com/alerts"
    assert payload["severity"] == "critical"

    assert incident_client.created == [(alert["id"], "auth")]


def test_repeated_breach_does_not_fire_a_second_alert(client, metrics_source, notifier):
    rule = _create_rule(client).json()
    metrics_source.value = 0.42

    client.post(f"/alerts/rules/{rule['id']}/evaluate")
    client.post(f"/alerts/rules/{rule['id']}/evaluate")
    client.post(f"/alerts/rules/{rule['id']}/evaluate")

    assert len(client.get("/alerts").json()) == 1
    assert len(notifier.sent) == 1  # not re-notified on every re-evaluation while still firing


def test_metric_recovering_resolves_the_alert(client, metrics_source):
    rule = _create_rule(client).json()
    metrics_source.value = 0.42
    client.post(f"/alerts/rules/{rule['id']}/evaluate")
    assert client.get("/alerts").json()[0]["status"] == "firing"

    metrics_source.value = 0.01
    client.post(f"/alerts/rules/{rule['id']}/evaluate")

    alert = client.get("/alerts").json()[0]
    assert alert["status"] == "resolved"
    assert alert["resolved_at"] is not None


def test_alert_fires_again_after_a_resolve_recover_cycle(client, metrics_source, notifier):
    rule = _create_rule(client).json()

    metrics_source.value = 0.42
    client.post(f"/alerts/rules/{rule['id']}/evaluate")  # fires
    metrics_source.value = 0.01
    client.post(f"/alerts/rules/{rule['id']}/evaluate")  # resolves
    metrics_source.value = 0.42
    client.post(f"/alerts/rules/{rule['id']}/evaluate")  # fires again -- a NEW alert, not the dedup path

    alerts = client.get("/alerts").json()
    assert len(alerts) == 2
    assert len(notifier.sent) == 2


def test_metrics_query_failure_does_not_crash_evaluation(client, metrics_source):
    rule = _create_rule(client).json()
    metrics_source.raise_error = True

    resp = client.post(f"/alerts/rules/{rule['id']}/evaluate")
    assert resp.status_code == 202  # accepted, evaluated safely, just found nothing to act on
    assert client.get("/alerts").json() == []


def test_webhook_failure_does_not_lose_the_alert(client, metrics_source, notifier, incident_client):
    rule = _create_rule(client).json()
    metrics_source.value = 0.42
    notifier.raise_error = True

    client.post(f"/alerts/rules/{rule['id']}/evaluate")

    alerts = client.get("/alerts").json()
    assert len(alerts) == 1  # still recorded even though notification failed
    assert alerts[0]["incident_id"] == "fake-incident-1"  # and incident linking still happened


def test_incident_service_failure_does_not_lose_the_alert(client, metrics_source, incident_client):
    rule = _create_rule(client).json()
    metrics_source.value = 0.42
    incident_client.raise_error = True

    client.post(f"/alerts/rules/{rule['id']}/evaluate")

    alerts = client.get("/alerts").json()
    assert len(alerts) == 1
    assert alerts[0]["incident_id"] is None  # link never completed, but the alert itself is intact


def test_inactive_rule_is_not_evaluated_by_evaluate_all(client, metrics_source, notifier):
    active = _create_rule(client, name="active rule").json()
    _create_rule(client, name="inactive rule", is_active=False)
    metrics_source.value = 0.99  # would breach either rule's threshold

    client.post("/alerts/evaluate-all")

    alerts = client.get("/alerts").json()
    assert len(alerts) == 1
    assert alerts[0]["rule_id"] == active["id"]


def test_evaluate_all_evaluates_every_active_rule(client, metrics_source):
    _create_rule(client, name="rule a", service_name="auth")
    _create_rule(client, name="rule b", service_name="gateway")
    metrics_source.value = 0.99

    client.post("/alerts/evaluate-all")

    alerts = client.get("/alerts").json()
    assert len(alerts) == 2


def test_acknowledge_alert(client, metrics_source):
    rule = _create_rule(client).json()
    metrics_source.value = 0.42
    client.post(f"/alerts/rules/{rule['id']}/evaluate")
    alert_id = client.get("/alerts").json()[0]["id"]

    resp = client.post(f"/alerts/{alert_id}/acknowledge")
    assert resp.status_code == 200
    assert resp.json()["acknowledged_at"] is not None
    # acknowledging doesn't resolve it -- still firing until the metric recovers
    assert resp.json()["status"] == "firing"


def test_get_alert_not_found(client):
    assert client.get("/alerts/does-not-exist").status_code == 404


def test_get_rule_not_found(client):
    assert client.get("/alerts/rules/does-not-exist").status_code == 404


def test_evaluate_nonexistent_rule_returns_404(client):
    assert client.post("/alerts/rules/does-not-exist/evaluate").status_code == 404


def test_list_rules_filters_by_service_name(client):
    _create_rule(client, service_name="auth")
    _create_rule(client, service_name="gateway", name="gateway rule")

    resp = client.get("/alerts/rules", params={"service_name": "gateway"})
    assert len(resp.json()) == 1
    assert resp.json()[0]["service_name"] == "gateway"


def test_list_alerts_filters_by_status_and_severity(client, metrics_source):
    critical_rule = _create_rule(client, severity="critical").json()
    warning_rule = _create_rule(
        client, name="latency", severity="warning", comparison="gt", threshold=1.0
    ).json()
    metrics_source.value = 999
    client.post(f"/alerts/rules/{critical_rule['id']}/evaluate")
    client.post(f"/alerts/rules/{warning_rule['id']}/evaluate")

    resp = client.get("/alerts", params={"severity": "warning"})
    assert len(resp.json()) == 1
    assert resp.json()[0]["severity"] == "warning"

    resp = client.get("/alerts", params={"status_filter": "firing"})
    assert len(resp.json()) == 2


def test_list_alerts_is_paginated(client, metrics_source):
    metrics_source.value = 999  # breaches every rule below, so each evaluate() actually fires an alert
    for i in range(5):
        rule = _create_rule(client, name=f"rule-{i}").json()
        client.post(f"/alerts/rules/{rule['id']}/evaluate")

    limited = client.get("/alerts", params={"limit": 2})
    assert len(limited.json()) == 2

    over_the_cap = client.get("/alerts", params={"limit": 500})
    assert over_the_cap.status_code == 422

    offset_page = client.get("/alerts", params={"limit": 2, "offset": 2})
    assert len(offset_page.json()) == 2
    assert {a["id"] for a in limited.json()}.isdisjoint({a["id"] for a in offset_page.json()})


def test_rule_without_webhook_still_fires_without_notifying(client, metrics_source, notifier):
    rule = _create_rule(client, webhook_url=None).json()
    metrics_source.value = 0.42

    client.post(f"/alerts/rules/{rule['id']}/evaluate")

    assert len(client.get("/alerts").json()) == 1
    assert notifier.sent == []


def test_comparison_operators(client, metrics_source):
    lt_rule = _create_rule(
        client, name="low disk space", comparison="lt", threshold=10.0, metric_query="disk_free_percent"
    ).json()

    metrics_source.value = 5.0  # 5 < 10 -> breached
    client.post(f"/alerts/rules/{lt_rule['id']}/evaluate")
    assert len(client.get("/alerts").json()) == 1


def test_acknowledge_emits_audit_event(client, metrics_source, audit_client):
    rule = _create_rule(client).json()
    metrics_source.value = 0.42
    client.post(f"/alerts/rules/{rule['id']}/evaluate")
    alert_id = client.get("/alerts").json()[0]["id"]

    client.post(f"/alerts/{alert_id}/acknowledge")

    calls = [c for c in audit_client.calls if c["action"] == "alert.acknowledged"]
    assert len(calls) == 1
    assert calls[0]["resource_id"] == alert_id
    assert calls[0]["actor"] == "system"
    assert "acknowledged_at" in calls[0]["after_state"]


def test_audit_failure_does_not_break_acknowledge(client, metrics_source, audit_client):
    rule = _create_rule(client).json()
    metrics_source.value = 0.42
    client.post(f"/alerts/rules/{rule['id']}/evaluate")
    alert_id = client.get("/alerts").json()[0]["id"]
    audit_client.raise_error = True

    resp = client.post(f"/alerts/{alert_id}/acknowledge")
    assert resp.status_code == 200
    assert resp.json()["acknowledged_at"] is not None


def test_create_rule_emits_audit_event(client, audit_client):
    rule = _create_rule(client).json()

    created = [c for c in audit_client.calls if c["action"] == "alert_rule.created"]
    assert len(created) == 1
    assert created[0]["resource_id"] == rule["id"]
    assert created[0]["after_state"]["name"] == rule["name"]


def test_audit_failure_does_not_break_rule_creation(client, audit_client):
    audit_client.raise_error = True
    resp = _create_rule(client)
    assert resp.status_code == 201


# --- Readiness vs liveness (Phase 6 follow-up) -----------------------------
#
# /health (liveness) and /health/ready (readiness) are deliberately
# different depths -- see app/main.py's own comments on each. These
# confirm the distinction actually works, not just that both endpoints
# exist.

def test_liveness_check_is_shallow_and_always_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "alert"}


def test_readiness_check_confirms_database_connectivity(client):
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready", "service": "alert"}


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
