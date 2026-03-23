"""Integration tests for the check_trip_eta ARQ job.

Tests the full flow: load trip → check cache → call MapKit → store snapshot
→ update trip → enqueue evaluate_alert. Uses real SQLite DB + mocked Redis
and MapKit client.
"""

from __future__ import annotations

import json
import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from app.models.enums import TripStatus
from app.models.trip import Trip
from app.models.trip_eta_snapshot import TripEtaSnapshot
from app.schemas.eta import EtaResult
from app.services.mapkit_api import MapKitError
from app.services.rate_limiter import RateLimitExceeded
from app.services.traffic_checker import check_trip_eta
from tests.conftest import test_session_factory


def _make_eta_result(
    duration: int = 2100,
    duration_in_traffic: int = 2580,
    distance: int = 77249,
) -> EtaResult:
    return EtaResult.from_route_response(duration, duration_in_traffic, distance)


def _build_ctx(
    mock_redis: AsyncMock,
    mock_routes_client: AsyncMock,
) -> dict:
    return {
        "db_session": test_session_factory,
        "redis": mock_redis,
        "routes_client": mock_routes_client,
    }


def _mock_redis(cached_value: str | None = None) -> AsyncMock:
    """Create a mock Redis with optional cached ETA."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=cached_value)
    redis.setex = AsyncMock()
    redis.enqueue_job = AsyncMock(return_value=None)
    # check_rate_limit calls redis.eval() and compares result > limit (int)
    redis.eval = AsyncMock(return_value=1)

    # increment_cost_counter uses pipeline with sync methods
    mock_pipe = MagicMock()
    mock_pipe.execute = AsyncMock(return_value=[1, True, 1, True])
    redis.pipeline = MagicMock(return_value=mock_pipe)
    return redis


@pytest.mark.asyncio
async def test_happy_path(db_session, test_user, make_trip) -> None:
    """Cache miss → API call → snapshot stored → trip updated → evaluate_alert enqueued."""
    trip = await make_trip(
        name="Commute",
        arrival_hours_from_now=2.0,
        status=TripStatus.monitoring,
    )

    eta = _make_eta_result()
    mock_routes = AsyncMock()
    mock_routes.compute_route = AsyncMock(return_value=eta)
    mock_redis = _mock_redis(cached_value=None)

    ctx = _build_ctx(mock_redis, mock_routes)
    await check_trip_eta(ctx, str(trip.id))

    # API was called
    mock_routes.compute_route.assert_called_once()

    # Snapshot was stored
    async with test_session_factory() as session:
        snaps = (
            await session.execute(
                select(TripEtaSnapshot).where(
                    TripEtaSnapshot.trip_id == trip.id
                )
            )
        ).scalars().all()
        assert len(snaps) == 1
        assert snaps[0].duration_in_traffic_seconds == 2580

    # Trip was updated
    async with test_session_factory() as session:
        updated = (
            await session.execute(select(Trip).where(Trip.id == trip.id))
        ).scalar_one()
        assert updated.last_eta_seconds == 2580
        assert updated.last_checked_at is not None
        assert updated.baseline_duration_seconds == 2100

    # evaluate_alert was enqueued
    mock_redis.enqueue_job.assert_called_once()
    args = mock_redis.enqueue_job.call_args.args
    assert args[0] == "_evaluate_alert"
    assert args[1] == str(trip.id)
    assert args[2] == 2580


@pytest.mark.asyncio
async def test_uses_cache_hit(db_session, test_user, make_trip) -> None:
    """Cached ETA → no API call → snapshot still stored."""
    trip = await make_trip(
        name="Cached Trip",
        arrival_hours_from_now=2.5,
        status=TripStatus.monitoring,
    )

    cached_eta = EtaResult.from_route_response(2100, 2400, 70000)
    cache_data = json.dumps(cached_eta.to_cache_dict())

    mock_routes = AsyncMock()
    mock_routes.compute_route = AsyncMock()
    mock_redis = _mock_redis(cached_value=cache_data)

    ctx = _build_ctx(mock_redis, mock_routes)
    await check_trip_eta(ctx, str(trip.id))

    # API should NOT have been called
    mock_routes.compute_route.assert_not_called()

    # Snapshot should still be stored
    async with test_session_factory() as session:
        snaps = (
            await session.execute(
                select(TripEtaSnapshot).where(
                    TripEtaSnapshot.trip_id == trip.id
                )
            )
        ).scalars().all()
        assert len(snaps) == 1
        assert snaps[0].duration_in_traffic_seconds == 2400

    # evaluate_alert still enqueued
    mock_redis.enqueue_job.assert_called_once()


@pytest.mark.asyncio
async def test_skips_stale_cache_in_critical_phase(
    db_session, test_user, make_trip
) -> None:
    """Cache >90s old + critical phase → fresh API call."""
    # For critical phase: 0 < time_until_notify ≤ 15 min
    # time_until_notify = arrival - eta - buffer - now
    # With arrival 2h=7200s, buffer 15min=900s, we need:
    #   eta = 7200 - 900 - ~300 = 6000s → ~100 min ETA
    trip = await make_trip(
        name="Critical Trip",
        arrival_hours_from_now=2.0,
        status=TripStatus.monitoring,
    )
    async with test_session_factory() as session:
        from sqlalchemy import update

        await session.execute(
            update(Trip)
            .where(Trip.id == trip.id)
            .values(last_eta_seconds=6000)  # ~100 min → time_until_notify ≈ 5 min → critical
        )
        await session.commit()

    # Stale cache (checked 2 minutes ago)
    stale_eta = EtaResult.from_route_response(2100, 2400, 70000)
    stale_data = stale_eta.to_cache_dict()
    stale_data["checked_at"] = (
        datetime.now(timezone.utc) - timedelta(seconds=120)
    ).isoformat()

    fresh_eta = _make_eta_result(2100, 3000, 77000)
    mock_routes = AsyncMock()
    mock_routes.compute_route = AsyncMock(return_value=fresh_eta)
    mock_redis = _mock_redis(cached_value=json.dumps(stale_data))

    ctx = _build_ctx(mock_redis, mock_routes)
    await check_trip_eta(ctx, str(trip.id))

    # API SHOULD have been called (cache was stale in critical phase)
    mock_routes.compute_route.assert_called_once()

    # Snapshot uses fresh value
    async with test_session_factory() as session:
        snaps = (
            await session.execute(
                select(TripEtaSnapshot).where(
                    TripEtaSnapshot.trip_id == trip.id
                )
            )
        ).scalars().all()
        assert len(snaps) == 1
        assert snaps[0].duration_in_traffic_seconds == 3000


@pytest.mark.asyncio
async def test_rate_limit_aborts_gracefully(
    db_session, test_user, make_trip
) -> None:
    """RateLimitExceeded → no API call, no snapshot, returns clean."""
    trip = await make_trip(
        name="Rate Limited Trip",
        arrival_hours_from_now=2.0,
        status=TripStatus.monitoring,
    )

    mock_routes = AsyncMock()
    mock_routes.compute_route = AsyncMock()

    mock_redis = _mock_redis(cached_value=None)
    mock_redis.eval = AsyncMock(
        side_effect=RateLimitExceeded("Limit hit", limit_type="global")
    )
    # check_rate_limit uses redis.eval internally; we need to mock
    # the check_rate_limit function instead
    mock_redis.get = AsyncMock(return_value=None)

    ctx = _build_ctx(mock_redis, mock_routes)

    # Patch check_rate_limit to raise
    import app.services.traffic_checker as tc_module
    original_check = tc_module.check_rate_limit

    async def _raise_rate_limit(*args, **kwargs):
        raise RateLimitExceeded("Limit hit", limit_type="global")

    tc_module.check_rate_limit = _raise_rate_limit
    try:
        await check_trip_eta(ctx, str(trip.id))
    finally:
        tc_module.check_rate_limit = original_check

    # No API call, no snapshot, no enqueue
    mock_routes.compute_route.assert_not_called()
    mock_redis.enqueue_job.assert_not_called()

    async with test_session_factory() as session:
        snaps = (
            await session.execute(
                select(TripEtaSnapshot).where(
                    TripEtaSnapshot.trip_id == trip.id
                )
            )
        ).scalars().all()
        assert len(snaps) == 0


@pytest.mark.asyncio
async def test_mapkit_error_propagates(
    db_session, test_user, make_trip
) -> None:
    """MapKitError → exception re-raised for ARQ retry."""
    trip = await make_trip(
        name="Error Trip",
        arrival_hours_from_now=2.0,
        status=TripStatus.monitoring,
    )

    mock_routes = AsyncMock()
    mock_routes.compute_route = AsyncMock(
        side_effect=MapKitError("Server error", status_code=500)
    )
    mock_redis = _mock_redis(cached_value=None)

    ctx = _build_ctx(mock_redis, mock_routes)

    with pytest.raises(MapKitError):
        await check_trip_eta(ctx, str(trip.id))


@pytest.mark.asyncio
async def test_skips_deleted_trip(db_session, test_user, make_trip) -> None:
    """is_deleted=True → returns immediately."""
    trip = await make_trip(
        name="Deleted Trip",
        arrival_hours_from_now=2.0,
        status=TripStatus.monitoring,
    )
    async with test_session_factory() as session:
        from sqlalchemy import update

        await session.execute(
            update(Trip).where(Trip.id == trip.id).values(is_deleted=True)
        )
        await session.commit()

    mock_routes = AsyncMock()
    mock_routes.compute_route = AsyncMock()
    mock_redis = _mock_redis()

    ctx = _build_ctx(mock_redis, mock_routes)
    await check_trip_eta(ctx, str(trip.id))

    mock_routes.compute_route.assert_not_called()
    mock_redis.enqueue_job.assert_not_called()


@pytest.mark.asyncio
async def test_skips_non_active_status(
    db_session, test_user, make_trip
) -> None:
    """status=completed → returns immediately."""
    trip = await make_trip(
        name="Completed Trip",
        arrival_hours_from_now=2.0,
        status=TripStatus.completed,
    )

    mock_routes = AsyncMock()
    mock_routes.compute_route = AsyncMock()
    mock_redis = _mock_redis()

    ctx = _build_ctx(mock_redis, mock_routes)
    await check_trip_eta(ctx, str(trip.id))

    mock_routes.compute_route.assert_not_called()
    mock_redis.enqueue_job.assert_not_called()
