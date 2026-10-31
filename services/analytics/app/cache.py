"""Redis-backed response cache for analytics' aggregation endpoints.

Every report here means at least one, and for /overview four, live HTTP
calls to other services (see service_clients.py) with no caching at all.
Fine at low traffic. A real problem at high traffic: a dashboard polling
/analytics/overview every few seconds, multiplied across however many
users have it open, turns into that same multiple of load landing on
deployment/incident/alert on top of whatever traffic they already have --
this is the one place in the platform where a single endpoint's load
scales with a THIRD PARTY's request rate (a browser polling on its own
schedule) rather than only with direct callers, which is exactly the
shape of thing that surprises people during a real traffic spike. A short
TTL cache absorbs that multiplication; the numbers being up to
CACHE_TTL_SECONDS stale doesn't matter for a stats dashboard the way it
would for, say, an incident's current status.
"""

import logging
from typing import Protocol

import redis

logger = logging.getLogger(__name__)


class CacheClient(Protocol):
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str, ttl_seconds: int) -> None: ...


class RedisCacheClient:
    def __init__(self, redis_url: str):
        # Short timeouts on purpose -- a slow or unreachable Redis must
        # fail fast into the "compute fresh" fallback (see get/set below),
        # never make a request wait on a cache that's having its own
        # problems. Caching is here to help under load, not to become a
        # second dependency that can make things worse than having no
        # cache at all.
        self._redis = redis.from_url(
            redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2
        )

    def get(self, key: str) -> str | None:
        try:
            return self._redis.get(key)
        except redis.RedisError:
            logger.warning("cache get failed, falling back to computing fresh", exc_info=True)
            return None

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        try:
            self._redis.setex(key, ttl_seconds, value)
        except redis.RedisError:
            logger.warning(
                "cache set failed -- this response won't be cached, next request computes fresh too",
                exc_info=True,
            )


_cache_client: CacheClient | None = None


def get_cache_client() -> CacheClient:
    global _cache_client
    if _cache_client is None:
        from .config import settings

        _cache_client = RedisCacheClient(settings.REDIS_URL)
    return _cache_client


def set_cache_client(client: CacheClient | None) -> None:
    """Test hook: inject an in-memory fake instead of a real Redis connection."""
    global _cache_client
    _cache_client = client
