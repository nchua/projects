"""Atomic Redis rate limiting using Lua scripts."""

from __future__ import annotations

import logging

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# Lua script for atomic increment + expire
# Returns the current count after increment
RATE_LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


class RateLimitExceeded(Exception):
    """Raised when a rate limit is hit."""

    def __init__(self, message: str, limit_type: str = "unknown") -> None:
        super().__init__(message)
        self.limit_type = limit_type


async def check_rate_limit(
    redis: aioredis.Redis,
    user_id: str,
    global_limit: int = 100,
    global_window_seconds: int = 60,
    user_limit: int = 30,
    user_window_seconds: int = 3600,
) -> None:
    """Check both global and per-user rate limits.

    Uses atomic Lua scripts to prevent race conditions between
    INCR and EXPIRE operations.

    Raises RateLimitExceeded if either limit is hit.
    """
    global_key = "ratelimit:google:global"
    user_key = f"ratelimit:google:user:{user_id}"

    # Check global limit
    global_count = await redis.eval(
        RATE_LIMIT_SCRIPT, 1, global_key, str(global_window_seconds)
    )
    if global_count > global_limit:
        raise RateLimitExceeded(
            f"Global rate limit hit ({global_count}/{global_limit})",
            limit_type="global",
        )

    # Check per-user limit
    user_count = await redis.eval(
        RATE_LIMIT_SCRIPT, 1, user_key, str(user_window_seconds)
    )
    if user_count > user_limit:
        raise RateLimitExceeded(
            f"User {user_id} rate limit hit ({user_count}/{user_limit})",
            limit_type="user",
        )


async def increment_cost_counter(
    redis: aioredis.Redis,
    provider: str = "google",
) -> None:
    """Track API call counts for cost monitoring."""
    from datetime import datetime, timezone

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily_key = f"metrics:api_calls:{date_str}"
    provider_key = f"metrics:provider:{provider}:{date_str}"

    pipe = redis.pipeline()
    pipe.incr(daily_key)
    pipe.expire(daily_key, 86400 * 2)  # 2 day TTL
    pipe.incr(provider_key)
    pipe.expire(provider_key, 86400 * 2)
    await pipe.execute()
