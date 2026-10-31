import os
import time

# Must be set before `app.config` is imported (Settings() runs at import time and
# refuses the built-in dev secret unless ICOP_ENV=local).
os.environ.setdefault("ICOP_ENV", "local")

import fakeredis
import jwt
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.core.redis_client import set_redis
from app.main import app


def make_token(
    role: str = "operator",
    token_type: str = "access",
    secret: str | None = None,
    expired: bool = False,
) -> str:
    """Build a JWT the same shape services/auth/app/security.py issues
    (same claim names, same HS256 algorithm) -- used both to give the
    `client` fixture a default valid token (see below) and, directly, by
    the negative-path tests in test_gateway.py that need a specific kind
    of invalid token (wrong secret, expired, wrong type).
    """
    now = time.time()
    payload = {
        "sub": "test-user@example.com",
        "role": role,
        "type": token_type,
        "iat": now,
        "exp": now - 60 if expired else now + 3600,
    }
    return jwt.encode(payload, secret if secret is not None else settings.SECRET_KEY, algorithm="HS256")


@pytest.fixture()
def fake_redis():
    fr = fakeredis.FakeAsyncRedis(decode_responses=True)
    set_redis(fr)
    yield fr
    set_redis(None)


@pytest.fixture(autouse=True)
def unavailable_upstreams(monkeypatch):
    """Keep gateway unit tests hermetic even when Compose services are up.

    Proxy tests that need an upstream explicitly mock the shared httpx
    client. Every other gateway test should observe the unavailable-upstream
    response, never accidentally call a developer's running local stack.
    """
    for field in (
        "AUTH_SERVICE_URL", "DEPLOYMENT_SERVICE_URL", "INCIDENT_SERVICE_URL",
        "ALERT_SERVICE_URL", "AIOPS_SERVICE_URL", "ANALYTICS_SERVICE_URL",
        "NOTIFICATION_SERVICE_URL", "AUDIT_SERVICE_URL", "INFRASTRUCTURE_SERVICE_URL",
    ):
        monkeypatch.setattr(settings, field, "http://127.0.0.1:1")


@pytest.fixture()
def client(fake_redis):
    # A valid token is attached to every request this client makes by
    # default -- every existing proxy/stub/rate-limit/metrics test in
    # test_gateway.py predates app/security.py's authentication
    # requirement and is testing something else entirely (proxy
    # forwarding, 501 stubs, rate limiting, metrics labeling); giving them
    # a default valid identity here means none of them had to be rewritten
    # to keep testing exactly what they always tested. Tests that
    # specifically exercise authentication itself (missing/invalid/expired
    # tokens, the public paths) override or clear this header per-call --
    # see test_gateway.py's "Authentication" section.
    with TestClient(app) as test_client:
        test_client.headers["Authorization"] = f"Bearer {make_token()}"
        yield test_client


@pytest.fixture(autouse=True)
def _pin_rate_limit_window(monkeypatch):
    """The limiter is fixed-window (`int(time.time() // window)`), so a test that
    fires RATE_LIMIT_REQUESTS requests and expects the next to be 429 fails if the
    clock crosses a window boundary mid-test (seen once in ~20 runs). Pin the
    limiter's clock; JWT expiry etc. keep using the real one."""
    import types

    from app.middleware import rate_limit

    monkeypatch.setattr(rate_limit, "time", types.SimpleNamespace(time=lambda: 1_000_000.0))
