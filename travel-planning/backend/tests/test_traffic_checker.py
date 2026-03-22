"""Unit tests for traffic checker — rate limiting and cache key logic."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.rate_limiter import RateLimitExceeded, check_rate_limit
from app.services.traffic_checker import _cache_key, _compute_api_departure_time


# --- cache key generation ---


class TestCacheKey:
    def test_basic_key(self) -> None:
        key = _cache_key(37.7749, -122.4194, 37.3382, -121.8863)
        assert key == "eta:37.7749_-122.4194:37.3382_-121.8863"

    def test_rounds_to_4_decimals(self) -> None:
        key1 = _cache_key(37.77491, -122.41941, 37.33821, -121.88631)
        key2 = _cache_key(37.77489, -122.41939, 37.33819, -121.88629)
        assert key1 == key2  # Same when rounded to 4dp

    def test_different_locations_different_keys(self) -> None:
        key1 = _cache_key(37.7749, -122.4194, 37.3382, -121.8863)
        key2 = _cache_key(37.7749, -122.4194, 34.0522, -118.2437)
        assert key1 != key2


# --- compute_api_departure_time ---


class TestComputeApiDepartureTime:
    def _make_trip(
        self,
        arrival_time: datetime,
        notify_at: datetime | None = None,
        last_eta_seconds: int | None = None,
        buffer_minutes: int = 15,
    ) -> MagicMock:
        trip = MagicMock()
        trip.arrival_time = arrival_time
        trip.notify_at = notify_at
        trip.last_eta_seconds = last_eta_seconds
        trip.buffer_minutes = buffer_minutes
        return trip

    def test_uses_notify_at_when_available(self) -> None:
        now = datetime.now(timezone.utc)
        notify_at = now + timedelta(minutes=30)
        trip = self._make_trip(
            arrival_time=now + timedelta(hours=2),
            notify_at=notify_at,
        )
        result = _compute_api_departure_time(trip)
        assert result == notify_at

    def test_uses_now_when_notify_at_is_past(self) -> None:
        now = datetime.now(timezone.utc)
        notify_at = now - timedelta(minutes=5)
        trip = self._make_trip(
            arrival_time=now + timedelta(minutes=30),
            notify_at=notify_at,
        )
        result = _compute_api_departure_time(trip)
        # Should be approximately now (within a few ms)
        assert result is not None
        assert abs((result - now).total_seconds()) < 1

    def test_returns_none_when_no_notify_at_and_no_eta(self) -> None:
        now = datetime.now(timezone.utc)
        trip = self._make_trip(
            arrival_time=now + timedelta(hours=2),
            notify_at=None,
            last_eta_seconds=None,
        )
        result = _compute_api_departure_time(trip)
        assert result is None

    def test_returns_none_when_too_far_future(self) -> None:
        now = datetime.now(timezone.utc)
        notify_at = now + timedelta(hours=4)
        trip = self._make_trip(
            arrival_time=now + timedelta(hours=6),
            notify_at=notify_at,
        )
        result = _compute_api_departure_time(trip)
        assert result is None


# --- rate limiting ---


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_under_limit_passes(self) -> None:
        redis = AsyncMock()
        redis.eval = AsyncMock(return_value=1)

        # Should not raise
        await check_rate_limit(redis, "user-123")

    @pytest.mark.asyncio
    async def test_global_limit_exceeded(self) -> None:
        redis = AsyncMock()
        # First call (global) returns 101, over the limit
        redis.eval = AsyncMock(return_value=101)

        with pytest.raises(RateLimitExceeded) as exc_info:
            await check_rate_limit(redis, "user-123")
        assert exc_info.value.limit_type == "global"

    @pytest.mark.asyncio
    async def test_user_limit_exceeded(self) -> None:
        redis = AsyncMock()
        # Global passes (10), user exceeds (31)
        redis.eval = AsyncMock(side_effect=[10, 31])

        with pytest.raises(RateLimitExceeded) as exc_info:
            await check_rate_limit(redis, "user-123")
        assert exc_info.value.limit_type == "user"

    @pytest.mark.asyncio
    async def test_exactly_at_limit_passes(self) -> None:
        redis = AsyncMock()
        # Global at 100, user at 30 — exactly at limits
        redis.eval = AsyncMock(side_effect=[100, 30])

        # Should not raise (limit is > not >=)
        await check_rate_limit(redis, "user-123")

    @pytest.mark.asyncio
    async def test_custom_limits(self) -> None:
        redis = AsyncMock()
        redis.eval = AsyncMock(side_effect=[51, 1])

        with pytest.raises(RateLimitExceeded):
            await check_rate_limit(
                redis, "user-123",
                global_limit=50, user_limit=10,
            )
