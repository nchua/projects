"""Integration tests for notification engine worker jobs.

Tests the async ARQ worker functions (scan_active_trips) with a real
SQLite test database and mocked Redis pool.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

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
    # Trip arriving in 1.5 hours — active phase (no prior ETA → rough estimate
    # ~6300s for SF→SJ; notify_at ≈ arrival - 6300s, well within active range)
    trip_active = await make_trip(
        name="Active Trip",
        arrival_hours_from_now=1.5,
        status=TripStatus.pending,
    )

    # Trip arriving in 0.5 hours — critical phase
    trip_critical = await make_trip(
        name="Critical Trip",
        arrival_hours_from_now=0.5,
        status=TripStatus.monitoring,
    )

    mock_redis = AsyncMock()
    mock_redis.enqueue_job = AsyncMock(return_value=None)
    ctx = _build_ctx(mock_redis)

    await scan_active_trips(ctx)

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

    await scan_active_trips(ctx)

    mock_redis.enqueue_job.assert_not_called()


@pytest.mark.asyncio
async def test_scan_transitions_pending_to_monitoring(
    db_session,
    test_user,
    make_trip,
) -> None:
    """A pending trip that gets enqueued should be transitioned to monitoring."""
    trip = await make_trip(
        name="Pending Trip",
        arrival_hours_from_now=1.0,
        status=TripStatus.pending,
    )
    trip_id = trip.id

    mock_redis = AsyncMock()
    mock_redis.enqueue_job = AsyncMock(return_value=None)
    ctx = _build_ctx(mock_redis)

    await scan_active_trips(ctx)

    # Verify the enqueue happened
    assert mock_redis.enqueue_job.call_count == 1

    # Re-query with a fresh session to see the committed status change
    async with test_session_factory() as fresh_session:
        stmt = select(Trip).where(Trip.id == trip_id)
        result = await fresh_session.execute(stmt)
        updated_trip = result.scalar_one()

        assert updated_trip.status == TripStatus.monitoring
        assert updated_trip.monitoring_started_at is not None
