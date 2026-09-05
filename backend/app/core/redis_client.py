"""Redis client factory used for caching, rate limiting and idempotency keys."""

from __future__ import annotations

from redis.asyncio import Redis, from_url

from app.config import get_settings

_redis_client: Redis | None = None


def get_redis() -> Redis:
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = from_url(settings.redis_url, decode_responses=True)
    return _redis_client


async def check_redis_health() -> bool:
    try:
        client = get_redis()
        return bool(await client.ping())
    except Exception:
        return False


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
