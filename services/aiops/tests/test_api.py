from app.llm_client import set_llm_client

from .fakes import FakeLLMClient, text_response, tool_use_response


def test_health(client):
    assert client.get("/health").status_code == 200


def test_explain_without_llm_configured_returns_503(client):
    # llm_client fixture leaves no LLM set -- the default, unconfigured state
    resp = client.post("/ai/explain", json={"service_name": "auth", "question": "why?"})
    assert resp.status_code == 503
    assert "ANTHROPIC_API_KEY" in resp.json()["detail"]


def test_explain_happy_path_gathers_evidence_and_logs_the_query(
    client, deployment_client, alert_client
):
    deployment_client.deployments = [{"id": "d1", "status": "failed", "image_tag": "v2"}]
    set_llm_client(
        FakeLLMClient(
            [
                tool_use_response("get_recent_deployments", {"service_name": "auth"}),
                text_response("The last deployment failed."),
            ]
        )
    )

    resp = client.post("/ai/explain", json={"service_name": "auth", "question": "why is it down?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "The last deployment failed."
    assert body["iterations"] == 2
    assert len(body["evidence"]) == 1
    assert body["evidence"][0]["tool"] == "get_recent_deployments"

    history = client.get("/ai/history").json()
    assert len(history) == 1
    assert history[0]["question"] == "why is it down?"
    assert history[0]["answer"] == "The last deployment failed."


def test_explain_rejects_empty_question(client):
    set_llm_client(FakeLLMClient([text_response("n/a")]))
    resp = client.post("/ai/explain", json={"service_name": "auth", "question": ""})
    assert resp.status_code == 422


def test_history_detail_includes_full_evidence(client, deployment_client):
    deployment_client.deployments = [{"id": "d1", "status": "succeeded"}]
    set_llm_client(
        FakeLLMClient(
            [
                tool_use_response("get_recent_deployments", {"service_name": "auth"}),
                text_response("All good."),
            ]
        )
    )
    client.post("/ai/explain", json={"service_name": "auth", "question": "any issues?"})
    query_id = client.get("/ai/history").json()[0]["id"]

    resp = client.get(f"/ai/history/{query_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["evidence"][0]["tool"] == "get_recent_deployments"
    assert body["evidence"][0]["result"]["deployments"] == [{"id": "d1", "status": "succeeded"}]


def test_history_detail_not_found(client):
    assert client.get("/ai/history/does-not-exist").status_code == 404


def test_history_filters_by_service_name(client):
    set_llm_client(FakeLLMClient([text_response("ok")] * 2))
    client.post("/ai/explain", json={"service_name": "auth", "question": "q1"})
    set_llm_client(FakeLLMClient([text_response("ok")]))
    client.post("/ai/explain", json={"service_name": "gateway", "question": "q2"})

    resp = client.get("/ai/history", params={"service_name": "gateway"})
    assert len(resp.json()) == 1
    assert resp.json()[0]["service_name"] == "gateway"


def test_explain_with_multiple_evidence_sources(
    client, deployment_client, alert_client, incident_client, metrics_client
):
    deployment_client.deployments = [{"id": "d1", "status": "succeeded"}]
    alert_client.alerts = [{"id": "a1", "severity": "warning"}]
    incident_client.incidents = []
    metrics_client.value = 0.02

    set_llm_client(
        FakeLLMClient(
            [
                tool_use_response("get_recent_deployments", {"service_name": "auth"}, call_id="c1"),
                tool_use_response("get_recent_alerts", {"service_name": "auth"}, call_id="c2"),
                tool_use_response("get_recent_incidents", {"service_name": "auth"}, call_id="c3"),
                tool_use_response("query_current_metric", {"promql": "up"}, call_id="c4"),
                text_response("Deployment succeeded, one warning-level alert, error rate is low."),
            ]
        )
    )

    resp = client.post("/ai/explain", json={"service_name": "auth", "question": "status check"})
    body = resp.json()
    assert body["iterations"] == 5
    tools_called = [e["tool"] for e in body["evidence"]]
    assert tools_called == [
        "get_recent_deployments",
        "get_recent_alerts",
        "get_recent_incidents",
        "query_current_metric",
    ]


# --- Readiness vs liveness (Phase 6 follow-up) -----------------------------
#
# /health (liveness) and /health/ready (readiness) are deliberately
# different depths -- see app/main.py's own comments on each. These
# confirm the distinction actually works, not just that both endpoints
# exist.

def test_liveness_check_is_shallow_and_always_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "aiops"}


def test_readiness_check_confirms_database_connectivity(client):
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready", "service": "aiops"}


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
