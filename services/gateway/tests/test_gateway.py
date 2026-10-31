from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from app.main import app

from .conftest import make_token


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_metrics(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200


def test_correlation_id_added_when_missing(client):
    resp = client.get("/health")
    assert "X-Correlation-ID" in resp.headers
    assert len(resp.headers["X-Correlation-ID"]) > 0


def test_correlation_id_echoed_when_provided(client):
    resp = client.get("/health", headers={"X-Correlation-ID": "test-id-123"})
    assert resp.headers["X-Correlation-ID"] == "test-id-123"


def test_correlation_id_present_even_on_rate_limited_response(client):
    # Regression test for the middleware-ordering note in app/main.py --
    # this fails if CorrelationIdMiddleware ever ends up wrapped INSIDE
    # the rate limiter instead of around it. Uses a stubbed (still-501)
    # route so hammering it stays instant and needs no mocking.
    from app.config import settings

    for _ in range(settings.RATE_LIMIT_REQUESTS):
        client.get("/api/v1/monitoring/list")

    resp = client.get("/api/v1/monitoring/list")
    assert resp.status_code == 429
    assert "X-Correlation-ID" in resp.headers


def test_unimplemented_service_returns_501_with_phase(client):
    resp = client.get("/api/v1/monitoring/list")
    assert resp.status_code == 501
    body = resp.json()
    assert "not implemented" in body["detail"]
    assert body["planned_for"]


def test_unimplemented_service_stub_covers_bare_path_too(client):
    resp = client.get("/api/v1/monitoring")
    assert resp.status_code == 501


def test_deployments_is_no_longer_stubbed(client):
    # "deployments" moved from NOT_YET_IMPLEMENTED to a real proxy route
    # once Phase 2 shipped. If a real deployment service isn't reachable
    # (as in this test, where nothing's mocked and nothing's listening on
    # DEPLOYMENT_SERVICE_URL), forwarding still fails cleanly as a 503,
    # never as the old 501 stub -- the two are easy to tell apart, and
    # this pins that "deployments" specifically is on the 503 (proxied)
    # path now, not the 501 (stub) path.
    resp = client.get("/api/v1/deployments")
    assert resp.status_code == 503


def test_alerts_and_incidents_are_no_longer_stubbed(client):
    # Same reasoning as test_deployments_is_no_longer_stubbed: with
    # nothing mocked and nothing listening on ALERT_SERVICE_URL /
    # INCIDENT_SERVICE_URL, forwarding fails cleanly as a 503 -- pinning
    # that these are on the proxy path now, not the old 501 stub path.
    assert client.get("/api/v1/alerts").status_code == 503
    assert client.get("/api/v1/incidents").status_code == 503


def test_all_still_unbuilt_services_stub_correctly(client):
    for service in ["monitoring"]:
        resp = client.get(f"/api/v1/{service}/anything")
        assert resp.status_code == 501, f"{service} did not return 501"
        assert service in resp.json()["detail"]


def test_ai_is_no_longer_stubbed(client):
    # Same reasoning as the deployments/alerts/incidents equivalents above.
    assert client.get("/api/v1/ai/history").status_code == 503


def test_analytics_notifications_audit_are_no_longer_stubbed(client):
    # Analytics' real endpoint requires a service scope. Supplying one
    # makes this the same 503-vs-501 proxy-path assertion as the other
    # checks, rather than accidentally asserting against the downstream
    # endpoint's legitimate 422 request validation.
    assert client.get("/api/v1/analytics/overview?service_name=gateway").status_code == 503
    assert client.get("/api/v1/notifications").status_code == 503
    assert client.get("/api/v1/audit/events").status_code == 503


def test_infrastructure_is_no_longer_stubbed(client):
    # "infrastructure" moved from NOT_YET_IMPLEMENTED to a real proxy route
    # once the Terraform/Ansible/GitOps pass shipped -- same reasoning as
    # every other "is no longer stubbed" test above: with nothing mocked
    # and nothing listening on INFRASTRUCTURE_SERVICE_URL, forwarding
    # fails cleanly as a 503, never as the old 501 stub.
    assert client.get("/api/v1/infrastructure/environments").status_code == 503


def test_rate_limit_blocks_after_threshold(client):
    from app.config import settings

    for _ in range(settings.RATE_LIMIT_REQUESTS):
        resp = client.get("/api/v1/monitoring/list")
        assert resp.status_code != 429

    resp = client.get("/api/v1/monitoring/list")
    assert resp.status_code == 429


def test_rate_limit_exempts_health_and_metrics(client):
    from app.config import settings

    for _ in range(settings.RATE_LIMIT_REQUESTS + 10):
        assert client.get("/health").status_code == 200
        assert client.get("/metrics").status_code == 200


def test_rate_limiter_fails_open_when_redis_is_unreachable(client):
    # Real gap this closes: before this fix, a Redis outage meant every
    # request through the gateway 500'd -- the rate limiter, a purely
    # auxiliary protection, was a hard dependency for the entire
    # platform's traffic. It must not be.
    from redis.exceptions import ConnectionError as RedisConnectionError

    with patch("app.middleware.rate_limit.get_redis") as mock_get_redis:
        broken_redis = AsyncMock()
        broken_redis.incr = AsyncMock(side_effect=RedisConnectionError("simulated Redis outage"))
        mock_get_redis.return_value = broken_redis

        resp = client.get("/api/v1/monitoring/list")
        # reached the real stub, not a 500 -- the outage was absorbed, not propagated
        assert resp.status_code == 501


def test_auth_proxy_forwards_to_auth_service(client):
    fake_response = httpx.Response(
        200,
        json={"status": "ok", "service": "auth"},
        request=httpx.Request("GET", "http://auth-service/auth/health"),
    )
    with patch("app.routers.proxy.get_http_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=fake_response)
        mock_get_client.return_value = mock_client

        resp = client.get("/api/v1/auth/health")

        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "service": "auth"}
        mock_client.request.assert_called_once()
        called_url = mock_client.request.call_args.args[1]
        assert called_url.endswith("/auth/health")


def test_auth_proxy_returns_503_when_auth_service_down(client):
    with patch("app.routers.proxy.get_http_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(side_effect=httpx.ConnectError("boom"))
        mock_get_client.return_value = mock_client

        resp = client.get("/api/v1/auth/health")
        assert resp.status_code == 503


def test_deployments_proxy_forwards_to_deployment_service(client):
    fake_response = httpx.Response(
        202,
        json={"id": "abc-123", "status": "succeeded"},
        request=httpx.Request("POST", "http://deployment-service/deployments"),
    )
    with patch("app.routers.proxy.get_http_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=fake_response)
        mock_get_client.return_value = mock_client

        resp = client.post(
            "/api/v1/deployments",
            json={"service_name": "auth", "environment": "local", "image_tag": "v1"},
        )

        assert resp.status_code == 202
        assert resp.json()["id"] == "abc-123"
        called_url = mock_client.request.call_args.args[1]
        assert called_url.endswith("/deployments")


def test_deployments_proxy_forwards_get_by_id(client):
    fake_response = httpx.Response(
        200,
        json={"id": "abc-123", "status": "succeeded"},
        request=httpx.Request("GET", "http://deployment-service/deployments/abc-123"),
    )
    with patch("app.routers.proxy.get_http_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=fake_response)
        mock_get_client.return_value = mock_client

        resp = client.get("/api/v1/deployments/abc-123")

        assert resp.status_code == 200
        called_url = mock_client.request.call_args.args[1]
        assert called_url.endswith("/deployments/abc-123")


def test_alerts_proxy_forwards_nested_rules_path(client):
    fake_response = httpx.Response(
        201,
        json={"id": "rule-1", "name": "high error rate"},
        request=httpx.Request("POST", "http://alert-service/alerts/rules"),
    )
    with patch("app.routers.proxy.get_http_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=fake_response)
        mock_get_client.return_value = mock_client

        resp = client.post(
            "/api/v1/alerts/rules",
            json={"name": "high error rate", "service_name": "auth", "metric_query": "up",
                  "comparison": "gt", "threshold": 0.05, "severity": "critical"},
        )

        assert resp.status_code == 201
        called_url = mock_client.request.call_args.args[1]
        assert called_url.endswith("/alerts/rules")


def test_incidents_proxy_forwards_to_incident_service(client):
    fake_response = httpx.Response(
        200,
        json=[{"id": "incident-1", "status": "open"}],
        request=httpx.Request("GET", "http://incident-service/incidents"),
    )
    with patch("app.routers.proxy.get_http_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=fake_response)
        mock_get_client.return_value = mock_client

        resp = client.get("/api/v1/incidents")

        assert resp.status_code == 200
        called_url = mock_client.request.call_args.args[1]
        assert called_url.endswith("/incidents")


def test_ai_proxy_forwards_explain_request(client):
    fake_response = httpx.Response(
        200,
        json={"answer": "The last deployment failed.", "evidence": [], "iterations": 2},
        request=httpx.Request("POST", "http://aiops-service/ai/explain"),
    )
    with patch("app.routers.proxy.get_http_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=fake_response)
        mock_get_client.return_value = mock_client

        resp = client.post(
            "/api/v1/ai/explain", json={"service_name": "auth", "question": "why did it fail?"}
        )

        assert resp.status_code == 200
        assert resp.json()["answer"] == "The last deployment failed."
        called_url = mock_client.request.call_args.args[1]
        assert called_url.endswith("/ai/explain")


def test_analytics_proxy_forwards_overview_request(client):
    fake_response = httpx.Response(
        200,
        json={"service_name": "auth", "deployments": {}, "incidents": {}, "alerts": {}},
        request=httpx.Request("GET", "http://analytics-service/analytics/overview"),
    )
    with patch("app.routers.proxy.get_http_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=fake_response)
        mock_get_client.return_value = mock_client

        resp = client.get("/api/v1/analytics/overview", params={"service_name": "auth"})

        assert resp.status_code == 200
        called_url = mock_client.request.call_args.args[1]
        assert called_url.endswith("/analytics/overview")


def test_notifications_proxy_forwards_to_notification_service(client):
    fake_response = httpx.Response(
        202,
        json={"id": "n1", "status": "sent"},
        request=httpx.Request("POST", "http://notification-service/notifications"),
    )
    with patch("app.routers.proxy.get_http_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=fake_response)
        mock_get_client.return_value = mock_client

        resp = client.post(
            "/api/v1/notifications",
            json={"channel": "webhook", "target": "https://x", "subject": "s", "body": "b"},
        )

        assert resp.status_code == 202
        called_url = mock_client.request.call_args.args[1]
        assert called_url.endswith("/notifications")


def test_audit_proxy_forwards_nested_events_path(client):
    fake_response = httpx.Response(
        200,
        json=[{"id": "a1", "action": "user.login"}],
        request=httpx.Request("GET", "http://audit-service/audit/events"),
    )
    with patch("app.routers.proxy.get_http_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=fake_response)
        mock_get_client.return_value = mock_client

        resp = client.get("/api/v1/audit/events")

        assert resp.status_code == 200
        called_url = mock_client.request.call_args.args[1]
        assert called_url.endswith("/audit/events")


def test_infrastructure_proxy_forwards_environments_path(client):
    fake_response = httpx.Response(
        202,
        json={"id": "e1", "status": "provisioning_infra"},
        request=httpx.Request("POST", "http://infrastructure-service/environments"),
    )
    with patch("app.routers.proxy.get_http_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=fake_response)
        mock_get_client.return_value = mock_client

        resp = client.post(
            "/api/v1/infrastructure/environments",
            json={"environment_type": "staging"},
            headers={"Authorization": f"Bearer {make_token(role='admin')}"},
        )

        assert resp.status_code == 202
        called_url = mock_client.request.call_args.args[1]
        assert called_url.endswith("/environments")


def test_unhandled_exception_returns_500_with_correlation_id(fake_redis):
    # Starlette's ServerErrorMiddleware calls our registered handler AND
    # sends its response, but then always re-raises the original exception
    # too (by design, so servers/tests can still see it). TestClient's
    # default raise_server_exceptions=True would surface that raise as a
    # test error instead of a response, so this test builds its own client
    # with that off, specifically to inspect what was actually sent back
    # -- and, since it bypasses the `client` fixture entirely to do that,
    # needs its own valid token too (see conftest.py's make_token) or it'd
    # hit app/security.py's 401 before ever reaching the mock below.
    with (
        patch("app.routers.proxy.get_http_client", side_effect=RuntimeError("boom")),
        TestClient(
            app, raise_server_exceptions=False, headers={"Authorization": f"Bearer {make_token()}"}
        ) as safe_client,
    ):
        resp = safe_client.get("/api/v1/auth/health")
        assert resp.status_code == 500
        assert resp.json()["correlation_id"]


def test_metrics_records_requests_including_rate_limited_ones(client):
    from app.config import settings

    for _ in range(settings.RATE_LIMIT_REQUESTS):
        client.get("/api/v1/monitoring/list")
    client.get("/api/v1/monitoring/list")  # this one gets 429'd

    body = client.get("/metrics").text
    assert 'http_requests_total{method="GET",path="/api/v1/monitoring/{path:path}",status="501"}' in body
    # The 429 is labeled "unmatched", not the route template -- the rate
    # limiter sits inside Metrics but outside routing, so a blocked
    # request never reaches the router and there genuinely is no route
    # template to attach to it yet.
    assert 'http_requests_total{method="GET",path="unmatched",status="429"}' in body


def test_metrics_records_unhandled_exceptions_as_500(fake_redis):
    with (
        patch("app.routers.proxy.get_http_client", side_effect=RuntimeError("boom")),
        TestClient(
            app, raise_server_exceptions=False, headers={"Authorization": f"Bearer {make_token()}"}
        ) as safe_client,
    ):
        safe_client.get("/api/v1/auth/health")
        body = safe_client.get("/metrics").text
    assert 'status="500"' in body


# --- Authentication (app/security.py) ---------------------------------
#
# Every test above uses the `client` fixture, which attaches a valid
# token by default (see conftest.py) specifically so none of them had to
# change when this requirement was added -- they were never testing
# authentication. These tests are.

def test_protected_route_without_any_token_is_rejected(client):
    resp = client.get("/api/v1/deployments", headers={"Authorization": ""})
    assert resp.status_code == 401
    assert resp.headers["WWW-Authenticate"] == "Bearer"


def test_protected_route_with_malformed_scheme_is_rejected(client):
    resp = client.get("/api/v1/deployments", headers={"Authorization": f"Token {make_token()}"})
    assert resp.status_code == 401


def test_protected_route_with_wrong_signature_is_rejected(client):
    forged = make_token(secret="not-the-real-secret")
    resp = client.get("/api/v1/deployments", headers={"Authorization": f"Bearer {forged}"})
    assert resp.status_code == 401
    assert "invalid" in resp.json()["detail"].lower()


def test_protected_route_with_expired_token_is_rejected(client):
    stale = make_token(expired=True)
    resp = client.get("/api/v1/deployments", headers={"Authorization": f"Bearer {stale}"})
    assert resp.status_code == 401


def test_protected_route_rejects_refresh_token_used_as_bearer(client):
    # A refresh token is real and validly signed -- just not meant to
    # authenticate an API call (see services/auth/app/routers/auth.py's
    # /auth/refresh, the one place a refresh token IS meant to be used).
    refresh_tok = make_token(token_type="refresh")
    resp = client.get("/api/v1/deployments", headers={"Authorization": f"Bearer {refresh_tok}"})
    assert resp.status_code == 401
    assert "refresh" in resp.json()["detail"].lower()


def test_stub_routes_also_require_authentication(client):
    # dependencies=[Depends(enforce_authentication)] is set on the router
    # itself (see routers/proxy.py), not on the real proxy routes
    # individually -- this confirms the still-501 stub routes are covered
    # by the same router-level dependency, not just the real proxies.
    resp = client.get("/api/v1/monitoring/list", headers={"Authorization": ""})
    assert resp.status_code == 401


def test_public_auth_paths_work_without_any_token(client):
    # register/login/refresh are the three routes app/security.py
    # explicitly allowlists (see PUBLIC_PATHS) -- calling them with NO
    # Authorization header at all must not 401. Nothing's mocked and
    # nothing's listening on AUTH_SERVICE_URL, so the real assertion is
    # "503 (reached the proxy, upstream unavailable), not 401 (rejected
    # before ever trying)" -- same pattern as every
    # test_*_is_no_longer_stubbed test above.
    for path, method in [
        ("/api/v1/auth/register", "post"),
        ("/api/v1/auth/login", "post"),
        ("/api/v1/auth/refresh", "post"),
    ]:
        resp = getattr(client, method)(path, headers={"Authorization": ""}, json={})
        assert resp.status_code == 503, f"{path} should be public, got {resp.status_code}"


def test_auth_me_and_users_are_not_public_despite_shared_prefix(client):
    # /auth/me and /auth/users are proxied through the exact same
    # generic "auth" route as register/login/refresh (see
    # routers/proxy.py's _register_proxy) -- this pins that
    # app/security.py's allowlist is genuinely path-exact, not a
    # "/api/v1/auth/*" prefix rule that would wrongly wave these two
    # through as well.
    assert client.get("/api/v1/auth/me", headers={"Authorization": ""}).status_code == 401
    assert client.get("/api/v1/auth/users", headers={"Authorization": ""}).status_code == 401


def test_health_and_metrics_stay_public(client):
    # Not under /api/v1 at all, so app/security.py's router-level
    # dependency never runs for these regardless of allowlist contents --
    # confirmed explicitly here so a future refactor that moved them under
    # the same router can't silently start requiring a token for the
    # endpoints load balancers and Prometheus itself depend on.
    assert client.get("/health", headers={"Authorization": ""}).status_code == 200
    assert client.get("/metrics", headers={"Authorization": ""}).status_code == 200


def test_readiness_endpoint_exists_and_is_public(client):
    # Real regression this guards against: infra/helm/service-chart's
    # readinessProbe points at /health/ready for every service using this
    # chart, gateway included (see values.yaml) -- if this endpoint
    # didn't exist, the gateway's own pods would never become Ready in a
    # real cluster, a 404 masquerading as "the chart works" until someone
    # actually deployed it.
    resp = client.get("/health/ready", headers={"Authorization": ""})
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready", "service": "gateway"}


def test_valid_token_claims_are_forwarded_to_upstream(client):
    fake_response = httpx.Response(
        200, json={"id": "abc-123"},
        request=httpx.Request("GET", "http://deployment-service/deployments/abc-123"),
    )
    token = make_token(role="admin")
    with patch("app.routers.proxy.get_http_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=fake_response)
        mock_get_client.return_value = mock_client

        client.get("/api/v1/deployments/abc-123", headers={"Authorization": f"Bearer {token}"})

        forwarded_headers = mock_client.request.call_args.kwargs["headers"]
        assert forwarded_headers["X-ICOP-User"] == "test-user@example.com"
        assert forwarded_headers["X-ICOP-Role"] == "admin"


def test_public_path_forwards_no_identity_headers(client):
    # register has no identity yet to forward -- confirms _proxy doesn't
    # add empty/placeholder X-ICOP-* headers for the one class of request
    # that legitimately has no claims at all.
    fake_response = httpx.Response(
        201, json={"id": "u1"}, request=httpx.Request("POST", "http://auth-service/auth/register"),
    )
    with patch("app.routers.proxy.get_http_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=fake_response)
        mock_get_client.return_value = mock_client

        client.post("/api/v1/auth/register", headers={"Authorization": ""}, json={})

        forwarded_headers = mock_client.request.call_args.kwargs["headers"]
        assert "X-ICOP-User" not in forwarded_headers
        assert "X-ICOP-Role" not in forwarded_headers


# --- Request body size limit (app/config.py's MAX_REQUEST_BODY_BYTES) --
#
# Only the backstop check (real body length, not the claimed
# Content-Length header) is tested here -- whether httpx's TestClient
# lets a manually-set Content-Length header override the one it computes
# from the real body isn't something this sandbox could execute and
# confirm either way, and a test whose own correctness is uncertain is
# worse than no test. The backstop is what actually matters for
# correctness regardless: it catches a lying OR absent Content-Length,
# which is the fast path's whole justification for existing.

def test_actually_oversized_body_is_rejected(client):
    with patch("app.config.settings.MAX_REQUEST_BODY_BYTES", 100):
        oversized_body = b"x" * 101
        resp = client.post("/api/v1/deployments", content=oversized_body)
        assert resp.status_code == 413


def test_body_within_limit_is_forwarded_normally(client):
    fake_response = httpx.Response(
        202, json={"id": "d1"}, request=httpx.Request("POST", "http://deployment-service/deployments"),
    )
    with patch("app.routers.proxy.get_http_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=fake_response)
        mock_get_client.return_value = mock_client

        resp = client.post("/api/v1/deployments", json={"service_name": "auth"})
        assert resp.status_code == 202


def test_docs_pages_get_a_csp_that_lets_swagger_render(client):
    # Regression: the blanket `default-src 'none'` CSP blocked Swagger UI's
    # CDN bundle and inline bootstrap script, so /docs was a blank page.
    docs = client.get("/docs")
    assert docs.status_code == 200
    csp = docs.headers["Content-Security-Policy"]
    assert "https://cdn.jsdelivr.net" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    # Every other response keeps the strict policy -- including a path that
    # merely starts with the same letters.
    for path in ("/health", "/api/v1/deployments", "/docsx"):
        other = client.get(path, headers={"Authorization": ""})
        assert "default-src 'none'; frame-ancestors 'none'" == other.headers["Content-Security-Policy"], path


def test_security_headers_present_on_success_and_error_responses(client):
    # SecurityHeadersMiddleware (app/middleware/security_headers.py) is
    # the outermost layer specifically so it covers error responses too,
    # not just 200s -- checked against both here, not just the happy path.
    ok = client.get("/health")
    assert ok.headers["X-Frame-Options"] == "DENY"
    assert ok.headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'none'" in ok.headers["Content-Security-Policy"]

    rejected = client.get("/api/v1/deployments", headers={"Authorization": ""})
    assert rejected.status_code == 401
    assert rejected.headers["X-Frame-Options"] == "DENY"


# --- Rate limiting IP resolution (app/middleware/rate_limit.py) --------

def test_x_forwarded_for_is_ignored_by_default(client):
    # TRUST_PROXY_HEADERS defaults False (see app/config.py) -- matches
    # today's real topology (no load balancer/ingress in front of this
    # gateway yet). A client claiming to be a different IP via
    # X-Forwarded-For must not actually change which rate-limit bucket it
    # lands in while this default holds, or the header becomes a free way
    # to dodge the limit entirely.
    from app.config import settings

    assert settings.TRUST_PROXY_HEADERS is False

    resp = client.get(
        "/api/v1/monitoring/list", headers={"X-Forwarded-For": "203.0.113.1"}
    )
    # Not a claim about status specifically -- just confirms the request
    # completes normally (reaches the stub, doesn't error) with a
    # spoofed header present, i.e. that the header had no special effect.
    assert resp.status_code == 501


def test_client_ip_helper_uses_rightmost_forwarded_entry_when_trusted():
    # Unit-level, not through the full app/client fixture -- isolates
    # app/middleware/rate_limit.py's _client_ip logic directly against a
    # minimal fake request, since exercising the "trusted" path through
    # the full stack would require monkeypatching settings mid-test in a
    # way that's easy to get subtly wrong (and easy to forget to undo).
    from unittest.mock import patch

    from app.middleware.rate_limit import _client_ip

    class FakeRequest:
        def __init__(self, headers, client_host="10.0.0.1"):
            self.headers = headers
            self.client = type("C", (), {"host": client_host})()

    with patch("app.middleware.rate_limit.settings.TRUST_PROXY_HEADERS", True):
        # "attacker-claimed, real-proxy-observed" -- the proxy's own
        # append (rightmost) is what should be trusted, not the client's
        # own claim (leftmost) -- see _client_ip's docstring for why.
        req = FakeRequest({"x-forwarded-for": "203.0.113.1, 198.51.100.7"})
        assert _client_ip(req) == "198.51.100.7"

        # No header at all -- falls back to the direct connection, same
        # as the untrusted path.
        req_no_header = FakeRequest({}, client_host="10.0.0.99")
        assert _client_ip(req_no_header) == "10.0.0.99"
