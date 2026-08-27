from app.ansible_orchestrator import set_ansible_orchestrator
from app.terraform_orchestrator import set_terraform_orchestrator

from .fakes import FakeAnsibleOrchestrator, FakeTerraformOrchestrator


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_create_environment_succeeds_end_to_end(client, terraform, ansible):
    resp = client.post("/environments", json={"environment_type": "staging"})
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "ready"
    assert body["name"].startswith("icop-staging-")
    assert body["cluster_name"] == "icop-staging"
    assert body["error_message"] is None
    assert terraform.applied == ["/terraform/environments/staging"]
    assert len(ansible.runs) == 1
    playbook_path, inventory_path, extra_vars = ansible.runs[0]
    assert playbook_path == "/ansible/playbooks/site.yml"
    assert inventory_path == "/ansible/inventory/aws_ec2.yml"
    assert extra_vars["ssm_transfer_bucket"] == "icop-staging-icop-ssm-transfer"


def test_create_environment_rejects_duplicate_of_same_type(client, terraform, ansible):
    first = client.post("/environments", json={"environment_type": "staging"})
    assert first.status_code == 202

    second = client.post("/environments", json={"environment_type": "staging"})
    assert second.status_code == 409
    assert "already exists" in second.json()["detail"]
    # Only the first request should have touched the orchestrators.
    assert terraform.applied == ["/terraform/environments/staging"]


def test_create_environment_allows_different_types_concurrently(client, terraform, ansible):
    staging = client.post("/environments", json={"environment_type": "staging"})
    production = client.post("/environments", json={"environment_type": "production"})
    assert staging.status_code == 202
    assert production.status_code == 202
    assert sorted(terraform.applied) == [
        "/terraform/environments/production",
        "/terraform/environments/staging",
    ]


def test_create_environment_rejects_invalid_type(client, terraform, ansible):
    resp = client.post("/environments", json={"environment_type": "not-a-real-env"})
    assert resp.status_code == 422


def test_terraform_apply_failure_marks_provision_failed_without_running_ansible(client, db_session):
    set_terraform_orchestrator(FakeTerraformOrchestrator(raise_on_apply=True))
    fake_ansible = FakeAnsibleOrchestrator()
    set_ansible_orchestrator(fake_ansible)

    resp = client.post("/environments", json={"environment_type": "staging"})
    body = resp.json()
    assert body["status"] == "provision_failed"
    assert "simulated terraform apply failure" in body["error_message"]
    assert body["cluster_name"] is None
    assert fake_ansible.runs == []  # never reached -- infra provisioning failed first


def test_ansible_failure_marks_provision_failed_but_keeps_cluster_name(client, db_session):
    fake_terraform = FakeTerraformOrchestrator()
    set_terraform_orchestrator(fake_terraform)
    set_ansible_orchestrator(FakeAnsibleOrchestrator(raise_on_run=True))

    resp = client.post("/environments", json={"environment_type": "staging"})
    body = resp.json()
    assert body["status"] == "provision_failed"
    assert "node configuration failed" in body["error_message"]
    # Terraform DID succeed -- real infrastructure exists, only the
    # Ansible step failed -- so cluster_name is still recorded rather than
    # silently dropped, matching executor.py's documented reasoning.
    assert body["cluster_name"] == "icop-staging"
    assert fake_terraform.applied == ["/terraform/environments/staging"]


def test_get_environment_returns_current_state(client, terraform, ansible):
    created = client.post("/environments", json={"environment_type": "staging"}).json()
    resp = client.get(f"/environments/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


def test_get_environment_not_found(client):
    resp = client.get("/environments/does-not-exist")
    assert resp.status_code == 404


def test_list_environments_filters_by_type(client, terraform, ansible):
    client.post("/environments", json={"environment_type": "staging"})
    client.post("/environments", json={"environment_type": "production"})

    resp = client.get("/environments", params={"environment_type": "production"})
    results = resp.json()
    assert len(results) == 1
    assert results[0]["environment_type"] == "production"


def test_destroy_environment_succeeds(client, terraform, ansible):
    created = client.post("/environments", json={"environment_type": "staging"}).json()

    resp = client.delete(f"/environments/{created['id']}")
    assert resp.status_code == 202
    assert resp.json()["status"] == "destroyed"
    assert terraform.destroyed == ["/terraform/environments/staging"]


def test_destroy_environment_not_found(client):
    resp = client.delete("/environments/does-not-exist")
    assert resp.status_code == 404


def test_destroy_environment_rejects_non_destroyable_status(client, db_session):
    # In eager-Celery test mode, a normal create request never observes an
    # in-progress status -- the task runs synchronously before the
    # response is built, so it always lands on a terminal status by the
    # time the caller sees it (see the tests above). To actually exercise
    # the destroy guard against a mid-provision row, insert one directly
    # rather than trying to race the real async flow.
    from app.models import Environment, EnvironmentStatus, EnvironmentType

    environment = Environment(
        name="icop-production",
        environment_type=EnvironmentType.production,
        status=EnvironmentStatus.provisioning_infra,
    )
    db_session.add(environment)
    db_session.commit()
    db_session.refresh(environment)

    resp = client.delete(f"/environments/{environment.id}")
    assert resp.status_code == 409
    assert "provisioning_infra" in resp.json()["detail"]


def test_terraform_destroy_failure_marks_destroy_failed(client, db_session):
    fake_terraform = FakeTerraformOrchestrator()
    set_terraform_orchestrator(fake_terraform)
    set_ansible_orchestrator(FakeAnsibleOrchestrator())

    created = client.post("/environments", json={"environment_type": "staging"}).json()
    assert created["status"] == "ready"

    fake_terraform.raise_on_destroy = True
    resp = client.delete(f"/environments/{created['id']}")
    body = resp.json()
    assert body["status"] == "destroy_failed"
    assert "simulated terraform destroy failure" in body["error_message"]


def test_environment_can_be_recreated_after_being_destroyed(client, terraform, ansible):
    first = client.post("/environments", json={"environment_type": "staging"}).json()
    client.delete(f"/environments/{first['id']}")

    second = client.post("/environments", json={"environment_type": "staging"})
    assert second.status_code == 202
    assert second.json()["id"] != first["id"]


def test_metrics_records_environment_requests(client, terraform, ansible):
    client.post("/environments", json={"environment_type": "staging"})
    body = client.get("/metrics").text
    assert 'http_requests_total{method="POST",path="/environments",status="202"}' in body


def test_create_environment_emits_triggered_and_ready_audit_events(client, terraform, ansible, audit_client):
    resp = client.post("/environments", json={"environment_type": "staging"})
    environment_id = resp.json()["id"]

    actions = [c["action"] for c in audit_client.calls if c["resource_id"] == environment_id]
    assert "environment.provision_triggered" in actions
    assert "environment.ready" in actions
    assert "environment.provision_failed" not in actions


def test_terraform_failure_emits_provision_failed_audit_event(client, db_session, audit_client):
    set_terraform_orchestrator(FakeTerraformOrchestrator(raise_on_apply=True))
    set_ansible_orchestrator(FakeAnsibleOrchestrator())

    resp = client.post("/environments", json={"environment_type": "staging"})
    environment_id = resp.json()["id"]

    failed_events = [
        c for c in audit_client.calls
        if c["resource_id"] == environment_id and c["action"] == "environment.provision_failed"
    ]
    assert len(failed_events) == 1
    assert "simulated terraform apply failure" in failed_events[0]["after_state"]["error"]


def test_destroy_emits_triggered_and_destroyed_audit_events(client, terraform, ansible, audit_client):
    created = client.post("/environments", json={"environment_type": "staging"}).json()
    client.delete(f"/environments/{created['id']}")

    actions = [c["action"] for c in audit_client.calls if c["resource_id"] == created["id"]]
    assert "environment.destroy_triggered" in actions
    assert "environment.destroyed" in actions


def test_audit_failure_does_not_break_environment_creation(client, terraform, ansible, audit_client):
    audit_client.raise_error = True
    resp = client.post("/environments", json={"environment_type": "staging"})
    assert resp.status_code == 202
    assert resp.json()["status"] == "ready"


def test_audit_failure_does_not_break_destroy(client, terraform, ansible, audit_client):
    created = client.post("/environments", json={"environment_type": "staging"}).json()
    audit_client.raise_error = True

    resp = client.delete(f"/environments/{created['id']}")
    assert resp.status_code == 202
    assert resp.json()["status"] == "destroyed"


# --- Readiness vs liveness (Phase 6 follow-up) -----------------------------
#
# /health (liveness) and /health/ready (readiness) are deliberately
# different depths -- see app/main.py's own comments on each. These
# confirm the distinction actually works, not just that both endpoints
# exist.

def test_liveness_check_is_shallow_and_always_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "infrastructure"}


def test_readiness_check_confirms_database_connectivity(client):
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready", "service": "infrastructure"}


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
