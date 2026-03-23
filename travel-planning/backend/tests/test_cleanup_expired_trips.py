"""Integration tests for the cleanup_expired_trips cron job.

Validates that trips past their arrival time get marked as completed.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from app.models.enums import TripStatus
from app.models.trip import Trip
from app.services.trip_scanner import cleanup_expired_trips
from tests.conftest import test_session_factory


def _build_ctx() -> dict:
    return {"db_session": test_session_factory}


@pytest.mark.asyncio
async def test_expired_trips_completed(
    db_session, test_user, make_trip
) -> None:
    """Trip with arrival 1h ago → status=completed."""
    trip = await make_trip(
        name="Expired Trip",
        arrival_hours_from_now=1.0,
        status=TripStatus.monitoring,
    )

    # Move arrival_time to 1 hour ago
    async with test_session_factory() as session:
        past_arrival = datetime.now(timezone.utc) - timedelta(hours=1)
        await session.execute(
            update(Trip)
            .where(Trip.id == trip.id)
            .values(arrival_time=past_arrival)
        )
        await session.commit()

    ctx = _build_ctx()
    await cleanup_expired_trips(ctx)

    async with test_session_factory() as session:
        updated = (
            await session.execute(select(Trip).where(Trip.id == trip.id))
        ).scalar_one()
        assert updated.status == TripStatus.completed


@pytest.mark.asyncio
async def test_skips_recent_trips(db_session, test_user, make_trip) -> None:
    """Trip with arrival 10min ago → status unchanged (within 30-min grace)."""
    trip = await make_trip(
        name="Recent Trip",
        arrival_hours_from_now=1.0,
        status=TripStatus.monitoring,
    )

    # Move arrival_time to 10 minutes ago (within 30-min cutoff)
    async with test_session_factory() as session:
        recent_arrival = datetime.now(timezone.utc) - timedelta(minutes=10)
        await session.execute(
            update(Trip)
            .where(Trip.id == trip.id)
            .values(arrival_time=recent_arrival)
        )
        await session.commit()

    ctx = _build_ctx()
    await cleanup_expired_trips(ctx)

    async with test_session_factory() as session:
        updated = (
            await session.execute(select(Trip).where(Trip.id == trip.id))
        ).scalar_one()
        assert updated.status == TripStatus.monitoring
