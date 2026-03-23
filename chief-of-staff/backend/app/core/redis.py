"""Redis connection utilities for ARQ worker."""

from urllib.parse import urlparse

from arq.connections import RedisSettings


def parse_redis_url(url: str) -> RedisSettings:
    """Parse a Redis URL into ARQ RedisSettings."""
    parsed = urlparse(url)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        password=parsed.password,
        database=int(parsed.path.lstrip("/") or 0),
        ssl=parsed.scheme == "rediss",
    )
