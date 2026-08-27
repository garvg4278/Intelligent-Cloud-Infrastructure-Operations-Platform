import redis.asyncio as redis_asyncio

from ..config import settings

_redis = None


def get_redis():
    global _redis
    if _redis is None:
        _redis = redis_asyncio.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def set_redis(client) -> None:
    """Test hook: inject a fake/mock redis client instead of a real one."""
    global _redis
    _redis = client
