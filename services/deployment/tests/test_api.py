from app.orchestrator import set_orchestrator

from .fakes import FakeOrchestrator


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_create_deployment_succeeds_with_healthy_orchestrator(client, orchestrator):
    resp = client.post(
        "/deployments", json={"service_name": "auth", "environment": "local", "image_tag": "v1.2.3"}
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "succeeded"
    assert body["revision"] == 1
    assert body["is_last_successful"] is True
    assert orchestrator.deployed == [("auth", {"image": {"repository": "auth", "tag": "v1.2.3"}})]


def test_create_deployment_rolls_back_on_failed_health_check(client, db_session):
    failing = FakeOrchestrator(fail_health_check=True)
    set_orchestrator(failing)

    resp = client.post(
        "/deployments", json={"service_name": "auth", "environment": "local", "image_tag": "v-bad"}
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "rolled_back"
    assert body["error_message"]
    assert failing.rolled_back == [("auth", None)]  # no prior success -> roll back to "whatever came before"


def test_rollback_targets_last_successful_revision(client, orchestrator):
    first = client.post(
        "/deployments", json={"service_name": "auth", "environment": "local", "image_tag": "v1"}
    ).json()
    assert first["status"] == "succeeded"
    assert first["revision"] == 1

    orchestrator.fail_health_check = True
    second = client.post(
        "/deployments", json={"service_name": "auth", "environment": "local", "image_tag": "v2-bad"}
    ).json()
    assert second["status"] == "rolled_back"
    assert orchestrator.rolled_back[-1] == ("auth", 1)  # rolled back to v1's revision


def test_deploy_time_failure_marks_failed_without_attempting_rollback(client, db_session):
    broken = FakeOrchestrator(raise_on_deploy=True)
    set_orchestrator(broken)

    resp = client.post(
        "/deployments", json={"service_name": "auth", "environment": "local", "image_tag": "v1"}
    )
    body = resp.json()
    assert body["status"] == "failed"
    assert broken.rolled_back == []


def test_get_deployment_returns_current_state(client, orchestrator):
    created = client.post(
        "/deployments", json={"service_name": "gateway", "environment": "staging", "image_tag": "v1"}
    ).json()

    resp = client.get(f"/deployments/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


def test_get_deployment_not_found(client):
    resp = client.get("/deployments/does-not-exist")
    assert resp.status_code == 404


def test_list_deployments_filters_by_service_name(client, orchestrator):
    client.post("/deployments", json={"service_name": "auth", "environment": "local", "image_tag": "v1"})
    client.post("/deployments", json={"service_name": "gateway", "environment": "local", "image_tag": "v1"})

    resp = client.get("/deployments", params={"service_name": "auth"})
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["service_name"] == "auth"


def test_list_deployments_filters_by_environment(client, orchestrator):
    client.post("/deployments", json={"service_name": "auth", "environment": "local", "image_tag": "v1"})
    client.post(
        "/deployments", json={"service_name": "auth", "environment": "production", "image_tag": "v1"}
    )

    resp = client.get("/deployments", params={"environment": "production"})
    results = resp.json()
    assert len(results) == 1
    assert results[0]["environment"] == "production"


def test_list_deployments_is_paginated(client, orchestrator):
    # Real gap this closes: this endpoint had no limit at all before --
    # see routers/deployments.py's own comment on why that's not
    # hypothetical for a service that's been deploying for months.
    for i in range(5):
        client.post(
            "/deployments", json={"service_name": "auth", "environment": "local", "image_tag": f"v{i}"}
        )

    limited = client.get("/deployments", params={"limit": 2})
    assert len(limited.json()) == 2

    over_the_cap = client.get("/deployments", params={"limit": 500})
    assert over_the_cap.status_code == 422  # rejected, not silently clamped -- see Query(..., le=200)

    offset_page = client.get("/deployments", params={"limit": 2, "offset": 2})
    assert len(offset_page.json()) == 2
    assert {d["id"] for d in limited.json()}.isdisjoint({d["id"] for d in offset_page.json()})


def test_create_deployment_rejects_invalid_environment(client, orchestrator):
    resp = client.post(
        "/deployments", json={"service_name": "auth", "environment": "not-a-real-env", "image_tag": "v1"}
    )
    assert resp.status_code == 422


def test_create_deployment_rejects_invalid_service_name(client, orchestrator):
    resp = client.post(
        "/deployments",
        json={"service_name": "Not_Valid_K8s_Name!", "environment": "local", "image_tag": "v1"},
    )
    assert resp.status_code == 422


def test_second_deployment_history_is_preserved(client, orchestrator):
    """Confirms mark_as_last_successful only flips the flag for the SAME
    service+environment, and that older successful deployments correctly
    lose the flag once a newer one succeeds -- both matter for rollback
    targeting to stay correct over time."""
    first = client.post(
        "/deployments", json={"service_name": "auth", "environment": "local", "image_tag": "v1"}
    ).json()
    second = client.post(
        "/deployments", json={"service_name": "auth", "environment": "local", "image_tag": "v2"}
    ).json()

    first_reloaded = client.get(f"/deployments/{first['id']}").json()
    second_reloaded = client.get(f"/deployments/{second['id']}").json()

    assert first_reloaded["is_last_successful"] is False
    assert second_reloaded["is_last_successful"] is True


def test_metrics_records_deployment_requests(client, orchestrator):
    client.post("/deployments", json={"service_name": "auth", "environment": "local", "image_tag": "v1"})
    body = client.get("/metrics").text
    assert 'http_requests_total{method="POST",path="/deployments",status="202"}' in body


def test_create_deployment_emits_triggered_audit_event(client, orchestrator, audit_client):
    resp = client.post(
        "/deployments", json={"service_name": "auth", "environment": "local", "image_tag": "v1"}
    )
    deployment_id = resp.json()["id"]

    triggered = [c for c in audit_client.calls if c["action"] == "deployment.triggered"]
    assert len(triggered) == 1
    assert triggered[0]["resource_id"] == deployment_id
    assert triggered[0]["after_state"]["image_tag"] == "v1"


def test_successful_deployment_does_not_emit_a_rollback_audit_event(client, orchestrator, audit_client):
    client.post("/deployments", json={"service_name": "auth", "environment": "local", "image_tag": "v1"})
    assert all(c["action"] != "deployment.rolled_back" for c in audit_client.calls)


def test_failed_health_check_emits_rollback_audit_event(client, db_session, audit_client):
    from app.orchestrator import set_orchestrator

    from .fakes import FakeOrchestrator

    failing = FakeOrchestrator(fail_health_check=True)
    set_orchestrator(failing)

    resp = client.post(
        "/deployments", json={"service_name": "auth", "environment": "local", "image_tag": "v-bad"}
    )
    deployment_id = resp.json()["id"]

    rollback_events = [c for c in audit_client.calls if c["action"] == "deployment.rolled_back"]
    assert len(rollback_events) == 1
    assert rollback_events[0]["resource_id"] == deployment_id
    assert rollback_events[0]["actor"] == "system"


def test_audit_failure_does_not_break_deployment_creation(client, orchestrator, audit_client):
    audit_client.raise_error = True
    resp = client.post(
        "/deployments", json={"service_name": "auth", "environment": "local", "image_tag": "v1"}
    )
    assert resp.status_code == 202
    assert resp.json()["status"] == "succeeded"


def test_audit_failure_does_not_break_a_rollback(client, db_session, audit_client):
    from app.orchestrator import set_orchestrator

    from .fakes import FakeOrchestrator

    set_orchestrator(FakeOrchestrator(fail_health_check=True))
    audit_client.raise_error = True

    resp = client.post(
        "/deployments", json={"service_name": "auth", "environment": "local", "image_tag": "v-bad"}
    )
    # The rollback itself must still succeed and be recorded even though
    # the audit call failed.
    assert resp.status_code == 202
    assert resp.json()["status"] == "rolled_back"


def test_successful_deployment_emits_succeeded_audit_event(client, orchestrator, audit_client):
    resp = client.post(
        "/deployments", json={"service_name": "auth", "environment": "local", "image_tag": "v1"}
    )
    deployment_id = resp.json()["id"]

    succeeded = [c for c in audit_client.calls if c["action"] == "deployment.succeeded"]
    assert len(succeeded) == 1
    assert succeeded[0]["resource_id"] == deployment_id


def test_deploy_time_failure_emits_failed_audit_event(client, db_session, audit_client):
    from app.orchestrator import set_orchestrator

    from .fakes import FakeOrchestrator

    set_orchestrator(FakeOrchestrator(raise_on_deploy=True))

    resp = client.post(
        "/deployments", json={"service_name": "auth", "environment": "local", "image_tag": "v1"}
    )
    deployment_id = resp.json()["id"]

    failed = [c for c in audit_client.calls if c["action"] == "deployment.failed"]
    assert len(failed) == 1
    assert failed[0]["resource_id"] == deployment_id
    assert "simulated deploy failure" in failed[0]["after_state"]["error"]


def test_successful_deployment_does_not_emit_a_failed_audit_event(client, orchestrator, audit_client):
    client.post("/deployments", json={"service_name": "auth", "environment": "local", "image_tag": "v1"})
    assert all(c["action"] != "deployment.failed" for c in audit_client.calls)


def test_rollback_emits_both_rolled_back_and_not_a_separate_failed_event(
    client, db_session, audit_client
):
    from app.orchestrator import set_orchestrator

    from .fakes import FakeOrchestrator

    set_orchestrator(FakeOrchestrator(fail_health_check=True))
    client.post("/deployments", json={"service_name": "auth", "environment": "local", "image_tag": "v1"})

    actions = [c["action"] for c in audit_client.calls]
    assert actions.count("deployment.rolled_back") == 1
    assert actions.count("deployment.failed") == 0  # rollback succeeded, so this isn't also "failed"


# --- Readiness vs liveness (Phase 6 follow-up) -----------------------------
#
# /health (liveness) and /health/ready (readiness) are deliberately
# different depths -- see app/main.py's own comments on each. These
# confirm the distinction actually works, not just that both endpoints
# exist.

def test_liveness_check_is_shallow_and_always_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "deployment"}


def test_readiness_check_confirms_database_connectivity(client):
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready", "service": "deployment"}


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


import pytest  # noqa: E402


@pytest.mark.parametrize(
    "bad_tag",
    [
        "v1,image.repository=docker.io/attacker/miner",   # Helm --set injection
        "v1,serviceAccount.name=privileged-sa",
        "v1 --set x=y",                                    # whitespace / flag smuggling
        "v1\nimage.tag=evil",                              # newline
        "-v1",                                             # leading dash looks like a CLI flag
        ".hidden",
        "a/b",                                             # registry path is not a tag
        "tag:with:colons",
        "{a,b}",
        "x" * 129,                                         # OCI max length is 128
    ],
)
def test_image_tag_outside_oci_grammar_is_rejected(client, orchestrator, bad_tag):
    resp = client.post(
        "/deployments", json={"service_name": "auth", "environment": "local", "image_tag": bad_tag}
    )
    assert resp.status_code == 422
    assert orchestrator.deployed == []  # nothing reached Helm


@pytest.mark.parametrize("good_tag", ["v1", "v1.2.3", "1.0.0-rc.1", "release_2026-10-30", "a" * 128])
def test_legitimate_image_tags_still_accepted(client, orchestrator, good_tag):
    resp = client.post(
        "/deployments", json={"service_name": "auth", "environment": "local", "image_tag": good_tag}
    )
    assert resp.status_code == 202
