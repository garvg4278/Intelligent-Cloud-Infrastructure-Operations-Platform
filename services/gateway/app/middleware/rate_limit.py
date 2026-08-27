import logging
import time

from fastapi import Request
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware

from ..config import settings
from ..core.redis_client import get_redis

logger = logging.getLogger(__name__)

EXEMPT_PATHS = {"/health", "/metrics"}


def _client_ip(request: Request) -> str:
    """request.client.host alone is only correct when nothing sits between
    the caller and this process. Today (plain `docker compose up`, no
    ingress/load balancer -- see gitops/bootstrap/argocd-values.yaml's own
    note that none is wired up yet) that's actually true, which is why
    TRUST_PROXY_HEADERS defaults False: turning this on before a real
    proxy exists would let any caller SET their own X-Forwarded-For header
    and rate-limit as whoever they claim to be instead of themselves --
    strictly worse than the current behavior, not a hardening. Once a real
    ALB/ingress sits in front of this gateway, it will set X-Forwarded-For
    itself (overwriting whatever a client tried to send), which is what
    makes trusting it safe -- flip this setting on at that point, not before.
    """
    if settings.TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # The proxy closest to this process appends last -- that's the
            # one entry a spoofing client can't have forged, since it's
            # the proxy's own connection, not a header value it merely
            # relayed. Every entry BEFORE that one could be attacker-
            # controlled if there's more than one hop, which is why this
            # takes the rightmost entry, not the leftmost (a common
            # mistake with X-Forwarded-For specifically).
            return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window rate limiter backed by Redis, keyed by client IP.

    Fixed window (not sliding/token-bucket) so the logic stays easy to
    reason about. Trade-off: a client can burst up to ~2x the limit right
    at a window boundary. Swap for a sliding-window or token-bucket
    algorithm if that turns out to matter in practice.
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        client_ip = _client_ip(request)
        window = int(time.time() // settings.RATE_LIMIT_WINDOW_SECONDS)
        key = f"ratelimit:{client_ip}:{window}"

        # Real gap this closes: Redis being briefly unreachable used to
        # mean every single request through the gateway 500'd -- the rate
        # limiter, a fundamentally auxiliary protection, was a hard
        # dependency for the entire platform's traffic. Failing open
        # (allow the request, skip rate limiting for this one check) is
        # the right trade-off here: a few seconds of unlimited traffic
        # during a Redis blip is a far smaller problem than the gateway
        # itself going down because of one.
        try:
            redis = get_redis()
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, settings.RATE_LIMIT_WINDOW_SECONDS)
        except RedisError:
            logger.warning("rate limiter Redis call failed, failing open for this request", exc_info=True)
            return await call_next(request)

        if count > settings.RATE_LIMIT_REQUESTS:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded, slow down."},
            )

        return await call_next(request)
