"""Integration tests for notification engine worker jobs.

Tests the async ARQ worker functions (scan_active_trips) with a real
SQLite test database and mocked Redis pool.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.models.enums import TripStatus
from app.models.trip import Trip
from app.services.trip_scanner import scan_active_trips
from tests.conftest import test_session_factory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_ctx(mock_redis: AsyncMock) -> dict:
    """Build the ARQ worker context dict with our test session factory."""
    return {
        "db_session": test_session_factory,
        "redis": mock_redis,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scan_enqueues_active_trips(
    db_session,
    test_user,
    make_trip,
) -> None:
    """Trips in the active/critical window should each get an ETA check enqueued."""
    # Rough ETA for SF→SJ is ~90 min (5400s). Phase uses:
    #   time_until_notify = arrival - rough_eta - buffer - now
    # Active phase: 15 min < time_until_notify ≤ 60 min
    #   → arrival_from_now between ~2h and ~2.75h
    trip_active = await make_trip(
        name="Active Trip",
        arrival_hours_from_now=2.5,
        status=TripStatus.pending,
    )

    # Critical phase: 0 < time_until_notify ≤ 15 min
    # Rough ETA for SF→SJ is ~101 min. notify_at = arrival - 101min - 15min
    # For critical: arrival_from_now needs ~2.0-2.1h
    trip_critical = await make_trip(
        name="Critical Trip",
        arrival_hours_from_now=2.1,
        status=TripStatus.monitoring,
    )

    mock_redis = AsyncMock()
    mock_redis.enqueue_job = AsyncMock(return_value=None)
    ctx = _build_ctx(mock_redis)

    # Pass naive UTC now — SQLite stores naive datetimes, so SQL comparisons
    # need naive values to match correctly.
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    await scan_active_trips(ctx, now=now_naive)

    # Both trips should have been enqueued
    assert mock_redis.enqueue_job.call_count == 2

    # Verify each call was for "_check_trip_eta" with the correct trip id
    enqueued_trip_ids = set()
    for call in mock_redis.enqueue_job.call_args_list:
        args = call.args
        assert args[0] == "_check_trip_eta"
        enqueued_trip_ids.add(args[1])

    assert str(trip_active.id) in enqueued_trip_ids
    assert str(trip_critical.id) in enqueued_trip_ids


@pytest.mark.asyncio
async def test_scan_skips_dormant_trips(
    db_session,
    test_user,
    make_trip,
) -> None:
    """A trip arriving in 5 hours is outside the 3.5h SQL window and ignored."""
    await make_trip(
        name="Dormant Trip",
        arrival_hours_from_now=5.0,
        status=TripStatus.pending,
    )

    mock_redis = AsyncMock()
    mock_redis.enqueue_job = AsyncMock(return_value=None)
    ctx = _build_ctx(mock_redis)

    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    await scan_active_trips(ctx, now=now_naive)

    mock_redis.enqueue_job.assert_not_called()


@pytest.mark.asyncio
async def test_scan_transitions_pending_to_monitoring(
    db_session,
    test_user,
    make_trip,
) -> None:
    """A pending trip that gets enqueued should be transitioned to monitoring."""
    # arrival_hours_from_now=2.5 puts this in the active phase
    # (rough ETA ~90 min + buffer 15 min leaves ~45 min until notify)
    trip = await make_trip(
        name="Pending Trip",
        arrival_hours_from_now=2.5,
        status=TripStatus.pending,
    )
    trip_id = trip.id

    mock_redis = AsyncMock()
    mock_redis.enqueue_job = AsyncMock(return_value=None)
    ctx = _build_ctx(mock_redis)

    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    await scan_active_trips(ctx, now=now_naive)

    # Verify the enqueue happened
    assert mock_redis.enqueue_job.call_count == 1

    # Re-query with a fresh session to see the committed status change
    async with test_session_factory() as fresh_session:
        stmt = select(Trip).where(Trip.id == trip_id)
        result = await fresh_session.execute(stmt)
        updated_trip = result.scalar_one()

        assert updated_trip.status == TripStatus.monitoring
        assert updated_trip.monitoring_started_at is not None
