def test_health(client):
    assert client.get("/health").status_code == 200


def test_readiness_endpoint_exists(client):
    # Real regression this guards against: infra/helm/service-chart's
    # readinessProbe points at /health/ready for every service using this
    # chart, analytics included -- without this endpoint, analytics' own
    # pods would never become Ready in a real cluster.
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready", "service": "analytics"}


def test_deployment_report(client, deployment_client):
    deployment_client.deployments = [
        {"status": "succeeded", "created_at": "2026-08-01T00:00:00Z"},
        {"status": "failed", "created_at": "2026-08-02T00:00:00Z"},
    ]
    resp = client.get("/analytics/deployments", params={"service_name": "auth"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 2
    assert resp.json()["success_rate"] == 0.5


def test_deployment_report_returns_503_when_deployment_service_down(client, deployment_client):
    deployment_client.raise_error = True
    resp = client.get("/analytics/deployments", params={"service_name": "auth"})
    assert resp.status_code == 503


def test_incident_report(client, incident_client):
    incident_client.incidents = [
        {
            "status": "resolved", "severity": "critical",
            "created_at": "2026-08-01T00:00:00Z", "resolved_at": "2026-08-01T02:00:00Z",
        }
    ]
    resp = client.get("/analytics/incidents", params={"service_name": "auth"})
    assert resp.status_code == 200
    assert resp.json()["avg_resolution_seconds"] == 7200.0


def test_alert_report(client, alert_client):
    alert_client.rules = [{"id": "r1", "name": "high errors"}]
    alert_client.alerts = [{"rule_id": "r1", "severity": "critical", "status": "firing"}]
    resp = client.get("/analytics/alerts", params={"service_name": "auth"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_overview_combines_all_three_sources(client, deployment_client, incident_client, alert_client):
    deployment_client.deployments = [{"status": "succeeded", "created_at": "2026-08-01T00:00:00Z"}]
    incident_client.incidents = []
    alert_client.rules = []
    alert_client.alerts = []

    resp = client.get("/analytics/overview", params={"service_name": "auth"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["service_name"] == "auth"
    assert body["deployments"]["total"] == 1
    assert body["incidents"]["total"] == 0
    assert body["alerts"]["total"] == 0


def test_overview_degrades_one_section_independently_on_failure(
    client, deployment_client, incident_client, alert_client
):
    # deployments source is down, but incidents/alerts still succeed --
    # the response should reflect that per-section, not fail entirely.
    deployment_client.raise_error = True
    incident_client.incidents = []
    alert_client.rules = []
    alert_client.alerts = []

    resp = client.get("/analytics/overview", params={"service_name": "auth"})
    assert resp.status_code == 200  # the overview endpoint itself still succeeds
    body = resp.json()
    assert "error" in body["deployments"]
    assert body["incidents"]["total"] == 0  # unaffected by the deployments failure


# --- Caching (app/cache.py) ---------------------------------------------

def test_second_identical_request_is_served_from_cache(client, deployment_client):
    deployment_client.deployments = [{"status": "succeeded", "created_at": "2026-08-01T00:00:00Z"}]

    first = client.get("/analytics/deployments", params={"service_name": "auth"})
    second = client.get("/analytics/deployments", params={"service_name": "auth"})

    assert first.json() == second.json()
    assert deployment_client.call_count == 1  # the second request never reached the fake client at all


def test_different_service_name_is_a_cache_miss(client, deployment_client):
    deployment_client.deployments = [{"status": "succeeded", "created_at": "2026-08-01T00:00:00Z"}]

    client.get("/analytics/deployments", params={"service_name": "auth"})
    client.get("/analytics/deployments", params={"service_name": "gateway"})

    assert deployment_client.call_count == 2  # different cache key each time -- no cross-contamination


def test_cache_set_uses_the_configured_ttl(client, deployment_client, cache_client):
    deployment_client.deployments = []
    client.get("/analytics/deployments", params={"service_name": "auth"})

    assert len(cache_client.set_calls) == 1
    _key, _value, ttl = cache_client.set_calls[0]
    assert ttl == 30


def test_failed_request_is_never_cached(client, deployment_client):
    deployment_client.raise_error = True

    first = client.get("/analytics/deployments", params={"service_name": "auth"})
    second = client.get("/analytics/deployments", params={"service_name": "auth"})

    assert first.status_code == 503
    assert second.status_code == 503
    assert deployment_client.call_count == 2  # never cached, so both requests actually tried


def test_fully_successful_overview_is_cached(
    client, deployment_client, incident_client, alert_client
):
    deployment_client.deployments = []
    incident_client.incidents = []
    alert_client.rules, alert_client.alerts = [], []

    client.get("/analytics/overview", params={"service_name": "auth"})
    client.get("/analytics/overview", params={"service_name": "auth"})

    assert deployment_client.call_count == 1
    assert incident_client.call_count == 1
    assert alert_client.call_count == 1


def test_degraded_overview_is_not_cached(client, deployment_client, incident_client, alert_client):
    # A temporary blip in one source shouldn't get frozen into the cache
    # for CACHE_TTL_SECONDS -- see routers/analytics.py's any_section_failed
    # check. Confirmed here by checking the failing source gets RETRIED on
    # the second request, not served a stale degraded response.
    deployment_client.raise_error = True
    incident_client.incidents = []
    alert_client.rules, alert_client.alerts = [], []

    client.get("/analytics/overview", params={"service_name": "auth"})
    client.get("/analytics/overview", params={"service_name": "auth"})

    assert deployment_client.call_count == 2  # retried both times, never cached


def test_cache_read_failure_degrades_to_computing_fresh(client, deployment_client, cache_client):
    # Simulates a Redis outage on the read path -- app/cache.py's real
    # RedisCacheClient.get() returns None (not an exception) when Redis
    # itself errors, which is exactly what FakeCacheClient(raise_on_get=True)
    # reproduces. The request must still succeed.
    cache_client.raise_on_get = True
    deployment_client.deployments = [{"status": "succeeded", "created_at": "2026-08-01T00:00:00Z"}]

    resp = client.get("/analytics/deployments", params={"service_name": "auth"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_cache_write_failure_degrades_to_uncached(client, deployment_client, cache_client):
    cache_client.raise_on_set = True
    deployment_client.deployments = []

    first = client.get("/analytics/deployments", params={"service_name": "auth"})
    second = client.get("/analytics/deployments", params={"service_name": "auth"})

    assert first.status_code == 200
    assert second.status_code == 200
    # The write never actually landed (raise_on_set), so nothing was ever
    # really cached -- both requests should have reached the fake client.
    assert deployment_client.call_count == 2
