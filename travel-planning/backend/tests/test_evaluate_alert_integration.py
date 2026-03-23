"""Integration tests for the evaluate_alert ARQ job.

Tests the full DB flow: load trip + user + notifications → run decision
logic → enqueue push notification if warranted.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.models.enums import (
    DeliveryStatus,
    NotificationType,
    TripStatus,
)
from app.models.notification_log import NotificationLog
from app.services.alert_evaluator import evaluate_alert
from tests.conftest import test_session_factory


def _build_ctx(mock_redis: AsyncMock) -> dict:
    return {
        "db_session": test_session_factory,
        "redis": mock_redis,
    }


@pytest.mark.asyncio
async def test_full_db_leave_now(db_session, test_user, make_trip) -> None:
    """Trip in leave_now zone → push enqueued with correct tier."""
    # Trip arriving in 50 min with a 45-min ETA and 15-min buffer
    # → recommended departure = arrival - 45min - 15min = now - 10min
    # → time_until_departure = -10 min → between -5 and 5 → leave_now? No, -10 < -5 → running_late
    # Let's adjust: arrival in 65 min, ETA 45 min, buffer 15 min
    # → departure = now + 65min - 45min - 15min = now + 5 min → leave_soon
    # For leave_now: departure = now ± 5 min
    # → arrival in 60 min, ETA 45 min, buffer 15 min
    # → departure = now + 0 min → leave_now (0 > -5)
    trip = await make_trip(
        name="Leave Now Trip",
        arrival_hours_from_now=1.0,  # 60 min
        buffer_minutes=15,
        status=TripStatus.monitoring,
    )
    # Set last_eta_seconds to 2700 (45 min) so departure = now + 0 min
    async with test_session_factory() as session:
        from sqlalchemy import update
        from app.models.trip import Trip

        await session.execute(
            update(Trip)
            .where(Trip.id == trip.id)
            .values(
                last_eta_seconds=2700,
                baseline_duration_seconds=2400,
            )
        )
        await session.commit()

    mock_redis = AsyncMock()
    mock_redis.enqueue_job = AsyncMock(return_value=None)
    ctx = _build_ctx(mock_redis)

    await evaluate_alert(ctx, str(trip.id), 2700)

    # Should have enqueued a send_push_notification
    mock_redis.enqueue_job.assert_called_once()
    args = mock_redis.enqueue_job.call_args.args
    assert args[0] == "_send_push_notification"
    assert args[1] == str(trip.id)
    assert args[2] == "leave_now"


@pytest.mark.asyncio
async def test_no_notification_when_insignificant(
    db_session, test_user, make_trip
) -> None:
    """Small ETA change → no push enqueued."""
    trip = await make_trip(
        name="Stable Trip",
        arrival_hours_from_now=2.0,
        buffer_minutes=15,
        status=TripStatus.monitoring,
    )
    async with test_session_factory() as session:
        from sqlalchemy import update
        from app.models.trip import Trip

        await session.execute(
            update(Trip)
            .where(Trip.id == trip.id)
            .values(
                last_eta_seconds=3600,
                baseline_duration_seconds=3600,
            )
        )
        await session.commit()

    # Insert an existing notification so there's a last_notified_eta
    async with test_session_factory() as session:
        log = NotificationLog(
            trip_id=trip.id,
            user_id=test_user.id,
            type=NotificationType.heads_up,
            title="Heads up",
            body="Light traffic",
            eta_at_send_seconds=3600,
            delivery_status=DeliveryStatus.delivered,
        )
        session.add(log)
        await session.commit()

    mock_redis = AsyncMock()
    mock_redis.enqueue_job = AsyncMock(return_value=None)
    ctx = _build_ctx(mock_redis)

    # ETA changed by only 60 seconds (well below 5-min / 10% threshold)
    await evaluate_alert(ctx, str(trip.id), 3660)

    mock_redis.enqueue_job.assert_not_called()


@pytest.mark.asyncio
async def test_anti_spam_blocks_5th_update(
    db_session, test_user, make_trip
) -> None:
    """4 existing prepare notifications → 5th prepare blocked by anti-spam."""
    # Need tier = prepare (15-60 min until departure)
    # arrival 2.5h = 9000s, buffer 15 min = 900s
    # For ~30 min departure offset: eta = 9000 - 900 - 1800 = 6300s
    trip = await make_trip(
        name="Spammy Trip",
        arrival_hours_from_now=2.5,
        buffer_minutes=15,
        status=TripStatus.monitoring,
    )
    async with test_session_factory() as session:
        from sqlalchemy import update
        from app.models.trip import Trip

        await session.execute(
            update(Trip)
            .where(Trip.id == trip.id)
            .values(
                last_eta_seconds=6300,
                baseline_duration_seconds=3000,
            )
        )
        await session.commit()

    # Insert 4 prepare notifications, last one >10 min ago
    async with test_session_factory() as session:
        base_time = datetime.now(timezone.utc) - timedelta(hours=2)
        for i in range(4):
            log = NotificationLog(
                trip_id=trip.id,
                user_id=test_user.id,
                type=NotificationType.prepare,
                title=f"Prepare {i+1}",
                body="Traffic update",
                eta_at_send_seconds=3000 + (i * 600),
                delivery_status=DeliveryStatus.delivered,
                sent_at=base_time + timedelta(minutes=i * 15),
            )
            session.add(log)
        await session.commit()

    mock_redis = AsyncMock()
    mock_redis.enqueue_job = AsyncMock(return_value=None)
    ctx = _build_ctx(mock_redis)

    # Significant ETA change but still in prepare tier, blocked by max-4 rule
    await evaluate_alert(ctx, str(trip.id), 6300)

    mock_redis.enqueue_job.assert_not_called()
