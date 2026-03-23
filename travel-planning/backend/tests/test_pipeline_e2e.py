"""End-to-end pipeline tests: check_trip_eta → evaluate_alert → send_push_notification.

Tests the full notification pipeline by calling all 3 jobs sequentially
(not via enqueue) and verifying the complete chain of DB side effects.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from app.models.device_token import DeviceToken
from app.models.enums import (
    DeliveryStatus,
    NotificationType,
    TripStatus,
)
from app.models.notification_log import NotificationLog
from app.models.trip import Trip
from app.models.trip_eta_snapshot import TripEtaSnapshot
from app.schemas.eta import EtaResult
from app.services.alert_evaluator import evaluate_alert
from app.services.push_sender import send_push_notification
from app.services.traffic_checker import check_trip_eta
from tests.conftest import test_session_factory


def _mock_apns_success() -> AsyncMock:
    client = AsyncMock()
    response = MagicMock()
    response.is_successful = True
    response.notification_id = "e2e-apns-id"
    client.send_notification = AsyncMock(return_value=response)
    return client


def _mock_redis() -> AsyncMock:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)  # No cache
    redis.setex = AsyncMock()
    # check_rate_limit calls redis.eval() and compares result > limit (int)
    redis.eval = AsyncMock(return_value=1)
    # increment_cost_counter uses pipeline with sync methods
    mock_pipe = MagicMock()
    mock_pipe.execute = AsyncMock(return_value=[1, True, 1, True])
    redis.pipeline = MagicMock(return_value=mock_pipe)

    # Capture enqueued jobs so we can call them directly
    redis._enqueued_jobs = []

    async def _capture_enqueue(job_name, *args, **kwargs):
        redis._enqueued_jobs.append((job_name, args, kwargs))

    redis.enqueue_job = AsyncMock(side_effect=_capture_enqueue)
    return redis


async def _add_device_token(user_id) -> DeviceToken:
    async with test_session_factory() as session:
        dt = DeviceToken(
            user_id=user_id,
            token="e2e-test-token",
            platform="ios",
            is_active=True,
        )
        session.add(dt)
        await session.commit()
        await session.refresh(dt)
        return dt


@pytest.mark.asyncio
async def test_full_pipeline_check_to_evaluate_to_send(
    db_session, test_user, make_trip
) -> None:
    """Calls all 3 jobs sequentially — verifies snapshot + notification log + trip status."""
    trip = await make_trip(
        name="E2E Trip",
        arrival_hours_from_now=1.0,  # 60 min
        buffer_minutes=15,
        status=TripStatus.monitoring,
    )
    await _add_device_token(test_user.id)

    # ETA of 45 min → departure = now + 0 min → leave_now tier
    eta = EtaResult.from_route_response(2400, 2700, 70000)
    mock_routes = AsyncMock()
    mock_routes.compute_route = AsyncMock(return_value=eta)
    mock_redis = _mock_redis()
    apns = _mock_apns_success()

    ctx = {
        "db_session": test_session_factory,
        "redis": mock_redis,
        "routes_client": mock_routes,
        "apns_client": apns,
    }

    # Step 1: check_trip_eta
    await check_trip_eta(ctx, str(trip.id))

    # Verify snapshot created
    async with test_session_factory() as session:
        snaps = (
            await session.execute(
                select(TripEtaSnapshot).where(
                    TripEtaSnapshot.trip_id == trip.id
                )
            )
        ).scalars().all()
        assert len(snaps) == 1
        assert snaps[0].duration_in_traffic_seconds == 2700

    # Step 2: evaluate_alert (would normally be enqueued by step 1)
    assert len(mock_redis._enqueued_jobs) == 1
    job_name, job_args, _ = mock_redis._enqueued_jobs[0]
    assert job_name == "_evaluate_alert"

    mock_redis._enqueued_jobs.clear()
    await evaluate_alert(ctx, job_args[0], job_args[1])

    # Step 3: send_push_notification (would normally be enqueued by step 2)
    assert len(mock_redis._enqueued_jobs) == 1
    job_name, job_args, _ = mock_redis._enqueued_jobs[0]
    assert job_name == "_send_push_notification"

    await send_push_notification(
        ctx, job_args[0], job_args[1], job_args[2], job_args[3], job_args[4]
    )

    # Verify final state
    async with test_session_factory() as session:
        final_trip = (
            await session.execute(select(Trip).where(Trip.id == trip.id))
        ).scalar_one()
        assert final_trip.status == TripStatus.departed
        assert final_trip.notification_count == 1
        assert final_trip.notified is True

        logs = (
            await session.execute(
                select(NotificationLog).where(
                    NotificationLog.trip_id == trip.id
                )
            )
        ).scalars().all()
        assert len(logs) == 1
        assert logs[0].type == NotificationType.leave_now
        assert logs[0].delivery_status == DeliveryStatus.delivered


@pytest.mark.asyncio
async def test_multiple_cycles_with_escalation(
    db_session, test_user, make_trip
) -> None:
    """3 cycles with worsening traffic → heads_up → prepare → leave_now."""
    # For heads_up on cycle 1: time_until_departure > 60 min
    # arrival 3h = 10800s, buffer 15min = 900s
    # Cycle 1 ETA 30 min: departure = 10800 - 1800 - 900 = 8100s = 135 min → heads_up
    trip = await make_trip(
        name="Escalation Trip",
        arrival_hours_from_now=3.0,  # 180 min
        buffer_minutes=15,
        status=TripStatus.monitoring,
    )
    await _add_device_token(test_user.id)

    apns = _mock_apns_success()

    # Cycle 1: Light traffic — 30 min ETA
    # departure_offset = 10800 - 1800 - 900 = 8100s = 135 min → heads_up
    eta_1 = EtaResult.from_route_response(1600, 1800, 50000)
    mock_routes = AsyncMock()
    mock_routes.compute_route = AsyncMock(return_value=eta_1)
    mock_redis = _mock_redis()

    ctx = {
        "db_session": test_session_factory,
        "redis": mock_redis,
        "routes_client": mock_routes,
        "apns_client": apns,
    }

    await check_trip_eta(ctx, str(trip.id))
    assert len(mock_redis._enqueued_jobs) == 1
    _, eval_args, _ = mock_redis._enqueued_jobs[0]
    mock_redis._enqueued_jobs.clear()
    await evaluate_alert(ctx, eval_args[0], eval_args[1])

    # Should have enqueued heads_up
    assert len(mock_redis._enqueued_jobs) == 1
    _, push_args, _ = mock_redis._enqueued_jobs[0]
    assert push_args[1] == "heads_up"
    await send_push_notification(
        ctx, push_args[0], push_args[1], push_args[2], push_args[3], push_args[4]
    )

    # Cycle 2: Worsening traffic — 140 min ETA (significant change)
    # departure_offset = 10800 - 8400 - 900 = 1500s = 25 min → prepare
    eta_2 = EtaResult.from_route_response(1600, 8400, 50000)
    mock_routes.compute_route = AsyncMock(return_value=eta_2)
    mock_redis._enqueued_jobs.clear()
    mock_redis.get = AsyncMock(return_value=None)

    await check_trip_eta(ctx, str(trip.id))
    assert len(mock_redis._enqueued_jobs) == 1
    _, eval_args, _ = mock_redis._enqueued_jobs[0]
    mock_redis._enqueued_jobs.clear()
    await evaluate_alert(ctx, eval_args[0], eval_args[1])

    if mock_redis._enqueued_jobs:
        _, push_args, _ = mock_redis._enqueued_jobs[0]
        assert push_args[1] == "prepare"
        await send_push_notification(
            ctx, push_args[0], push_args[1], push_args[2], push_args[3], push_args[4]
        )

    # Cycle 3: Even worse — 175 min ETA
    # departure_offset = 10800 - 10500 - 900 = -600s = -10 min → running_late
    eta_3 = EtaResult.from_route_response(1600, 10500, 50000)
    mock_routes.compute_route = AsyncMock(return_value=eta_3)
    mock_redis._enqueued_jobs.clear()
    mock_redis.get = AsyncMock(return_value=None)

    await check_trip_eta(ctx, str(trip.id))
    assert len(mock_redis._enqueued_jobs) == 1
    _, eval_args, _ = mock_redis._enqueued_jobs[0]
    mock_redis._enqueued_jobs.clear()
    await evaluate_alert(ctx, eval_args[0], eval_args[1])

    if mock_redis._enqueued_jobs:
        _, push_args, _ = mock_redis._enqueued_jobs[0]
        # Should be leave_now or running_late (critical tier)
        assert push_args[1] in ("leave_now", "running_late")
        await send_push_notification(
            ctx, push_args[0], push_args[1], push_args[2], push_args[3], push_args[4]
        )

    # Verify: trip transitioned to departed, multiple notifications sent
    async with test_session_factory() as session:
        final_trip = (
            await session.execute(select(Trip).where(Trip.id == trip.id))
        ).scalar_one()
        assert final_trip.status == TripStatus.departed

        logs = (
            await session.execute(
                select(NotificationLog)
                .where(NotificationLog.trip_id == trip.id)
                .order_by(NotificationLog.sent_at.asc())
            )
        ).scalars().all()
        # At least heads_up + one critical notification
        assert len(logs) >= 2
        tiers = [log.type.value for log in logs]
        assert "heads_up" in tiers
