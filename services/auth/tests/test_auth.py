from app import crud, models, schemas


def test_register_and_login(client):
    resp = client.post("/auth/register", json={"email": "alice@example.com", "password": "supersecret1"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "alice@example.com"
    assert body["role"] == "viewer"

    resp = client.post("/auth/login", data={"username": "alice@example.com", "password": "supersecret1"})
    assert resp.status_code == 200
    tokens = resp.json()
    assert "access_token" in tokens and "refresh_token" in tokens


def test_register_duplicate_email_rejected(client):
    client.post("/auth/register", json={"email": "bob@example.com", "password": "supersecret1"})
    resp = client.post("/auth/register", json={"email": "bob@example.com", "password": "anotherpassword"})
    assert resp.status_code == 400


def test_register_rejects_short_password(client):
    resp = client.post("/auth/register", json={"email": "short@example.com", "password": "short"})
    assert resp.status_code == 422


def test_login_wrong_password_rejected(client):
    client.post("/auth/register", json={"email": "carol@example.com", "password": "supersecret1"})
    resp = client.post("/auth/login", data={"username": "carol@example.com", "password": "wrongpass"})
    assert resp.status_code == 401


def test_login_unknown_user_rejected(client):
    resp = client.post("/auth/login", data={"username": "ghost@example.com", "password": "whatever1"})
    assert resp.status_code == 401


def test_me_requires_token(client):
    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_me_rejects_garbage_token(client):
    resp = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


def test_me_returns_current_user(client):
    client.post("/auth/register", json={"email": "dave@example.com", "password": "supersecret1"})
    login = client.post("/auth/login", data={"username": "dave@example.com", "password": "supersecret1"})
    token = login.json()["access_token"]
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "dave@example.com"


def test_users_list_requires_admin_role(client):
    client.post("/auth/register", json={"email": "erin@example.com", "password": "supersecret1"})
    login = client.post("/auth/login", data={"username": "erin@example.com", "password": "supersecret1"})
    token = login.json()["access_token"]
    resp = client.get("/auth/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_admin_can_list_users(client, db_session):
    client.post("/auth/register", json={"email": "greg@example.com", "password": "supersecret1"})
    crud.create_user(
        db_session,
        schemas.UserCreate(email="admin@example.com", password="supersecret1"),
        role=models.Role.admin,
    )

    login = client.post("/auth/login", data={"username": "admin@example.com", "password": "supersecret1"})
    token = login.json()["access_token"]

    resp = client.get("/auth/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    emails = {u["email"] for u in resp.json()}
    assert {"greg@example.com", "admin@example.com"} <= emails


def test_refresh_token_issues_new_access_token(client):
    client.post("/auth/register", json={"email": "frank@example.com", "password": "supersecret1"})
    login = client.post("/auth/login", data={"username": "frank@example.com", "password": "supersecret1"})
    refresh_token = login.json()["refresh_token"]
    resp = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_refresh_rejects_access_token_used_as_refresh(client):
    client.post("/auth/register", json={"email": "gail@example.com", "password": "supersecret1"})
    login = client.post("/auth/login", data={"username": "gail@example.com", "password": "supersecret1"})
    access_token = login.json()["access_token"]
    resp = client.post("/auth/refresh", json={"refresh_token": access_token})
    assert resp.status_code == 401


def test_health_check(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_metrics_endpoint_exposes_prometheus_format(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]


def test_metrics_records_request_count_and_latency_by_route_template(client):
    client.post("/auth/register", json={"email": "metrics-test@example.com", "password": "supersecret1"})
    client.post("/auth/register", json={"email": "metrics-test@example.com", "password": "supersecret1"})

    resp = client.get("/metrics")
    body = resp.text
    # Labeled with the ROUTE TEMPLATE (/auth/register), not per-request data
    assert 'http_requests_total{method="POST",path="/auth/register",status="201"}' in body
    assert 'http_requests_total{method="POST",path="/auth/register",status="400"}' in body
    assert "http_request_duration_seconds" in body


def test_metrics_records_unmatched_paths_without_leaking_the_raw_path(client):
    client.get("/this/path/does/not/exist")
    body = client.get("/metrics").text
    assert 'path="unmatched"' in body
    assert "/this/path/does/not/exist" not in body


def test_register_emits_audit_event(client, audit_client):
    resp = client.post("/auth/register", json={"email": "audited@example.com", "password": "supersecret1"})
    user_id = resp.json()["id"]

    assert len(audit_client.calls) == 1
    call = audit_client.calls[0]
    assert call["actor"] == "audited@example.com"
    assert call["action"] == "user.registered"
    assert call["resource_type"] == "user"
    assert call["resource_id"] == user_id


def test_login_emits_audit_event(client, audit_client):
    client.post("/auth/register", json={"email": "audited2@example.com", "password": "supersecret1"})
    audit_client.calls.clear()  # only care about the login event now

    client.post("/auth/login", data={"username": "audited2@example.com", "password": "supersecret1"})

    assert len(audit_client.calls) == 1
    assert audit_client.calls[0]["action"] == "user.login"
    assert audit_client.calls[0]["actor"] == "audited2@example.com"


def test_failed_login_for_unknown_email_does_not_emit_an_audit_event(client, audit_client):
    # The audit trail is append-only and kept forever: attempts against
    # arbitrary attacker-chosen strings must not be able to fill it.
    resp = client.post("/auth/login", data={"username": "nobody@example.com", "password": "wrong"})
    assert resp.status_code == 401
    assert audit_client.calls == []


def test_audit_service_failure_does_not_break_registration(client, audit_client):
    audit_client.raise_error = True
    resp = client.post("/auth/register", json={"email": "resilient@example.com", "password": "supersecret1"})
    # Registration itself must succeed even though the audit call failed
    assert resp.status_code == 201


def test_audit_service_failure_does_not_break_login(client, audit_client):
    client.post("/auth/register", json={"email": "resilient2@example.com", "password": "supersecret1"})
    audit_client.raise_error = True

    resp = client.post("/auth/login", data={"username": "resilient2@example.com", "password": "supersecret1"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


# --- Readiness vs liveness (Phase 6 follow-up) -----------------------------
#
# /health (liveness) and /health/ready (readiness) are deliberately
# different depths -- see app/main.py's own comments on each. These
# confirm the distinction actually works, not just that both endpoints
# exist.

def test_liveness_check_is_shallow_and_always_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "auth"}


def test_readiness_check_confirms_database_connectivity(client):
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready", "service": "auth"}


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
