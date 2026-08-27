def _create(client, **overrides):
    payload = {
        "actor": "alice@example.com",
        "action": "deployment.created",
        "resource_type": "deployment",
        "resource_id": "dep-123",
        "source_service": "deployment",
    }
    payload.update(overrides)
    return client.post("/audit/events", json=payload)


def test_health(client):
    assert client.get("/health").status_code == 200


def test_create_event(client):
    resp = _create(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["actor"] == "alice@example.com"
    assert body["action"] == "deployment.created"


def test_create_event_with_before_after_state_round_trips_as_real_json(client):
    resp = _create(
        client,
        action="role.updated",
        before_state={"role": "viewer"},
        after_state={"role": "operator"},
    )
    body = resp.json()
    assert body["before_state"] == {"role": "viewer"}
    assert body["after_state"] == {"role": "operator"}


def test_create_event_without_before_after_state_is_null_not_empty_dict(client):
    resp = _create(client)
    body = resp.json()
    assert body["before_state"] is None
    assert body["after_state"] is None


def test_get_event_not_found(client):
    assert client.get("/audit/events/does-not-exist").status_code == 404


def test_get_event_returns_full_detail(client):
    created = _create(client).json()
    resp = client.get(f"/audit/events/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


def test_list_filters_by_actor(client):
    _create(client, actor="alice@example.com")
    _create(client, actor="bob@example.com")

    resp = client.get("/audit/events", params={"actor": "bob@example.com"})
    assert len(resp.json()) == 1
    assert resp.json()[0]["actor"] == "bob@example.com"


def test_list_filters_by_action(client):
    _create(client, action="user.login")
    _create(client, action="deployment.created")

    resp = client.get("/audit/events", params={"action": "user.login"})
    assert len(resp.json()) == 1


def test_list_filters_by_resource_type(client):
    _create(client, resource_type="deployment")
    _create(client, resource_type="user")

    resp = client.get("/audit/events", params={"resource_type": "user"})
    assert len(resp.json()) == 1


def test_list_filters_by_source_service(client):
    _create(client, source_service="auth")
    _create(client, source_service="deployment")

    resp = client.get("/audit/events", params={"source_service": "auth"})
    assert len(resp.json()) == 1
    assert resp.json()[0]["source_service"] == "auth"


def test_list_combines_multiple_filters(client):
    _create(client, actor="alice@example.com", action="user.login")
    _create(client, actor="alice@example.com", action="deployment.created")
    _create(client, actor="bob@example.com", action="user.login")

    resp = client.get("/audit/events", params={"actor": "alice@example.com", "action": "user.login"})
    assert len(resp.json()) == 1


def test_list_orders_most_recent_first(client):
    _create(client, action="first")
    _create(client, action="second")
    _create(client, action="third")

    actions = [e["action"] for e in client.get("/audit/events").json()]
    assert actions == ["third", "second", "first"]


def test_there_is_no_way_to_mutate_or_delete_an_event(client):
    created = _create(client).json()
    event_id = created["id"]

    # None of these routes exist -- this pins that down at the HTTP level,
    # not just by reading routers/audit.py and trusting no one adds one.
    assert client.put(f"/audit/events/{event_id}", json={"actor": "changed"}).status_code == 405
    assert client.patch(f"/audit/events/{event_id}", json={"actor": "changed"}).status_code == 405
    assert client.delete(f"/audit/events/{event_id}").status_code == 405

    # And the record is provably unchanged
    assert client.get(f"/audit/events/{event_id}").json() == created


# --- Pagination -----------------------------------------------------------
#
# The one list endpoint in the platform designed to grow forever by
# definition (see routers/audit.py's own comment on this) -- these are
# deliberately more thorough than the equivalent tests on the other three
# services this same fix touched (deployment/incident/alert), since this
# is the highest-consequence instance of the gap it closes.

def test_list_events_default_limit_is_fifty(client):
    for i in range(55):
        _create(client, resource_id=f"dep-{i}")
    resp = client.get("/audit/events")
    assert len(resp.json()) == 50


def test_list_events_respects_explicit_limit(client):
    for i in range(10):
        _create(client, resource_id=f"dep-{i}")
    resp = client.get("/audit/events", params={"limit": 3})
    assert len(resp.json()) == 3


def test_list_events_limit_is_capped_at_two_hundred(client):
    resp = client.get("/audit/events", params={"limit": 5000})
    assert resp.status_code == 422  # rejected outright, not silently clamped -- see Query(..., le=200)


def test_list_events_offset_skips_correctly(client):
    # Created oldest-first; the endpoint orders newest-first (see
    # crud.list_events's order_by(created_at.desc())) -- so offset=0
    # returns the LAST one created, offset=1 the one before that.
    ids = []
    for i in range(5):
        resp = _create(client, resource_id=f"dep-{i}")
        ids.append(resp.json()["id"])

    first_page = client.get("/audit/events", params={"limit": 1, "offset": 0}).json()
    second_page = client.get("/audit/events", params={"limit": 1, "offset": 1}).json()

    assert first_page[0]["id"] == ids[-1]
    assert second_page[0]["id"] == ids[-2]
    assert first_page[0]["id"] != second_page[0]["id"]


def test_list_events_pagination_combines_with_filters(client):
    for i in range(5):
        _create(client, actor="paginated@example.com", resource_id=f"dep-{i}")
    _create(client, actor="someone-else@example.com")

    resp = client.get(
        "/audit/events", params={"actor": "paginated@example.com", "limit": 2, "offset": 0}
    )
    body = resp.json()
    assert len(body) == 2
    assert all(e["actor"] == "paginated@example.com" for e in body)


# --- Readiness vs liveness (Phase 6 follow-up) -----------------------------
#
# /health (liveness) and /health/ready (readiness) are deliberately
# different depths -- see app/main.py's own comments on each. These
# confirm the distinction actually works, not just that both endpoints
# exist.

def test_liveness_check_is_shallow_and_always_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "audit"}


def test_readiness_check_confirms_database_connectivity(client):
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready", "service": "audit"}


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
