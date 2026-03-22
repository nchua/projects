"""Async Redis connection pool."""

import redis.asyncio as redis

from app.core.config import get_settings

_pool: redis.Redis | None = None


async def get_redis_pool() -> redis.Redis:
    """Get or create the Redis connection pool."""
    global _pool
    if _pool is None:
        _pool = redis.from_url(
            get_settings().redis_url,
            decode_responses=True,
        )
    return _pool


async def close_redis_pool() -> None:
    """Close the Redis connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
