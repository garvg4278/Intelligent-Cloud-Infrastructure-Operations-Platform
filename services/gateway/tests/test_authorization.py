"""Authorization + request-hardening tests for the gateway.

Every test here encodes something that was demonstrably exploitable before
the Phase 8 hardening pass (see ROADMAP.md): a registered `viewer` could
provision cloud infrastructure, anyone logged in could forge audit events,
a token with no `exp` was valid forever, `..%2f` escaped the service
prefix, and a client could set its own X-ICOP-Role header.
"""

import time
from unittest.mock import AsyncMock, patch

import httpx
import jwt
import pytest

from app.config import settings

from .conftest import make_token


def _bearer(role: str) -> dict:
    return {"Authorization": f"Bearer {make_token(role=role)}"}


@pytest.fixture()
def upstream():
    """Patch the shared upstream client; yields the AsyncMock so tests can
    assert both on the response AND on whether anything was forwarded."""
    ok = httpx.Response(200, json={"ok": True}, request=httpx.Request("GET", "http://upstream/x"))
    with patch("app.routers.proxy.get_http_client") as get_client:
        mock = AsyncMock()
        mock.request = AsyncMock(return_value=ok)
        get_client.return_value = mock
        yield mock


# ---- role matrix -------------------------------------------------------

@pytest.mark.parametrize(
    ("role", "method", "path", "allowed"),
    [
        # read-only: every role may read the operational APIs
        ("viewer", "GET", "/api/v1/deployments", True),
        ("viewer", "GET", "/api/v1/incidents", True),
        ("viewer", "GET", "/api/v1/analytics/overview", True),
        # mutations need operator, not just a login
        ("viewer", "POST", "/api/v1/deployments", False),
        ("developer", "POST", "/api/v1/deployments", False),
        ("operator", "POST", "/api/v1/deployments", True),
        ("viewer", "POST", "/api/v1/alerts/rules", False),
        ("operator", "POST", "/api/v1/alerts/rules", True),
        ("viewer", "POST", "/api/v1/notifications", False),
        # AI costs money but is read-only: developer and up
        ("viewer", "POST", "/api/v1/ai/explain", False),
        ("developer", "POST", "/api/v1/ai/explain", True),
        # provisioning/destroying real cloud infrastructure is admin-only
        ("viewer", "GET", "/api/v1/infrastructure/environments", False),
        ("operator", "GET", "/api/v1/infrastructure/environments", True),
        ("operator", "POST", "/api/v1/infrastructure/environments", False),
        ("operator", "DELETE", "/api/v1/infrastructure/environments/e1", False),
        ("admin", "POST", "/api/v1/infrastructure/environments", True),
        ("admin", "DELETE", "/api/v1/infrastructure/environments/e1", True),
        # audit trail is sensitive to read
        ("viewer", "GET", "/api/v1/audit/events", False),
        ("operator", "GET", "/api/v1/audit/events", True),
        # analytics is computed, never written
        ("admin", "POST", "/api/v1/analytics/overview", False),
    ],
)
def test_role_matrix(client, upstream, role, method, path, allowed):
    resp = client.request(method, path, headers=_bearer(role), json={} if method != "GET" else None)
    if allowed:
        assert resp.status_code == 200, resp.text
        upstream.request.assert_called_once()
    else:
        assert resp.status_code == 403, resp.text
        upstream.request.assert_not_called()


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_nobody_can_write_audit_events_through_the_gateway(client, upstream, method):
    """Even an admin. Services write audit events over the internal network;
    an API caller writing them would make the 'immutable' trail forgeable."""
    resp = client.request(method, "/api/v1/audit/events", headers=_bearer("admin"), json={})
    assert resp.status_code == 403
    upstream.request.assert_not_called()


def test_unknown_role_claim_is_rejected(client, upstream):
    resp = client.get("/api/v1/deployments", headers=_bearer("superuser"))
    assert resp.status_code == 403
    upstream.request.assert_not_called()


# ---- token strictness ----------------------------------------------------

def test_token_without_exp_is_rejected(client, upstream):
    """PyJWT only checks `exp` when it is present; unsigned-lifetime tokens
    used to be valid forever."""
    forever = jwt.encode(
        {"sub": "a@b.test", "role": "admin", "type": "access"}, settings.SECRET_KEY, algorithm="HS256"
    )
    resp = client.get("/api/v1/deployments", headers={"Authorization": f"Bearer {forever}"})
    assert resp.status_code == 401
    upstream.request.assert_not_called()


def test_token_without_sub_is_rejected(client, upstream):
    no_sub = jwt.encode(
        {"role": "admin", "type": "access", "exp": time.time() + 60}, settings.SECRET_KEY, algorithm="HS256"
    )
    resp = client.get("/api/v1/deployments", headers={"Authorization": f"Bearer {no_sub}"})
    assert resp.status_code == 401


# ---- identity header spoofing ---------------------------------------------

def test_client_supplied_identity_headers_are_overwritten_not_forwarded(client, upstream):
    resp = client.get(
        "/api/v1/deployments",
        headers={**_bearer("viewer"), "X-ICOP-Role": "admin", "X-ICOP-User": "ceo@corp.test"},
    )
    assert resp.status_code == 200
    sent = {k.lower(): v for k, v in upstream.request.call_args.kwargs["headers"].items()}
    assert sent["x-icop-role"] == "viewer"
    assert sent["x-icop-user"] == "test-user@example.com"


def test_client_supplied_identity_headers_are_dropped_on_public_paths(client, upstream):
    client.post(
        "/api/v1/auth/login",
        headers={"Authorization": "", "X-ICOP-Role": "admin", "X-ICOP-User": "ceo@corp.test"},
        data={"username": "a", "password": "b"},
    )
    sent = {k.lower() for k in upstream.request.call_args.kwargs["headers"]}
    assert not any(k.startswith("x-icop-") for k in sent)


# ---- path traversal ---------------------------------------------------------

@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/deployments/..%2fmetrics",
        "/api/v1/deployments/%2e%2e/metrics",
        "/api/v1/deployments/a/%2e%2e/%2e%2e/health",
        "/api/v1/deployments/a%5c..%5cmetrics",
    ],
)
def test_path_traversal_out_of_service_prefix_is_rejected(client, upstream, path):
    resp = client.get(path, headers=_bearer("admin"))
    assert resp.status_code in (400, 404)
    upstream.request.assert_not_called()


def test_encoded_query_delimiters_stay_path_data(client, upstream):
    """%3f must not turn the rest of the path into an upstream query string."""
    client.get("/api/v1/deployments/abc%3fadmin=1", headers=_bearer("viewer"))
    url = upstream.request.call_args.args[1]
    assert "?" not in url
    assert url.endswith("/deployments/abc%3Fadmin%3D1") or url.endswith("/deployments/abc%3Fadmin=1")


# ---- timeouts -----------------------------------------------------------------

def test_ai_route_gets_a_longer_upstream_timeout_than_other_routes(client, upstream):
    client.get("/api/v1/deployments", headers=_bearer("viewer"))
    default_timeout = upstream.request.call_args.kwargs["timeout"]
    client.post("/api/v1/ai/explain", headers=_bearer("developer"), json={})
    ai_timeout = upstream.request.call_args.kwargs["timeout"]
    assert ai_timeout > default_timeout >= 1


# ---- startup guard on weak secrets ------------------------------------------------

def test_default_secret_refused_outside_local_env():
    from app.config import Settings

    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(ICOP_ENV="production", SECRET_KEY="dev-secret-change-me")


def test_short_secret_refused_outside_local_env():
    from app.config import Settings

    with pytest.raises(ValueError, match="32 bytes"):
        Settings(ICOP_ENV="staging", SECRET_KEY="too-short")


def test_strong_secret_accepted_outside_local_env():
    from app.config import Settings

    assert Settings(ICOP_ENV="production", SECRET_KEY="x" * 40).SECRET_KEY == "x" * 40


def test_dev_secret_tolerated_only_in_local_env():
    from app.config import Settings

    assert Settings(ICOP_ENV="local").SECRET_KEY == "dev-secret-change-me"
