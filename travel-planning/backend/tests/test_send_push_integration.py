"""Integration tests for the send_push_notification ARQ job.

Tests the full DB flow: load trip + user → build notification → send via
APNs → log result → update trip status.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from sqlalchemy import select

from app.models.device_token import DeviceToken
from app.models.enums import DeliveryStatus, NotificationType, TripStatus
from app.models.notification_log import NotificationLog
from app.models.trip import Trip
from app.services.push_sender import send_push_notification
from tests.conftest import test_session_factory


def _build_ctx(
    apns_client: AsyncMock | None = None,
) -> dict:
    return {
        "db_session": test_session_factory,
        "apns_client": apns_client,
    }


async def _add_device_token(
    user_id, token_str: str = "abc123token", is_active: bool = True
) -> DeviceToken:
    async with test_session_factory() as session:
        dt = DeviceToken(
            user_id=user_id,
            token=token_str,
            platform="ios",
            is_active=is_active,
        )
        session.add(dt)
        await session.commit()
        await session.refresh(dt)
        return dt


def _mock_apns_success() -> AsyncMock:
    """APNs client that returns successful responses."""
    client = AsyncMock()
    response = MagicMock()
    response.is_successful = True
    response.notification_id = "apns-uuid-123"
    client.send_notification = AsyncMock(return_value=response)
    return client


def _mock_apns_unregistered() -> AsyncMock:
    """APNs client that returns Unregistered (stale token)."""
    client = AsyncMock()
    response = MagicMock()
    response.is_successful = False
    response.description = "Unregistered"
    response.status = "410"
    client.send_notification = AsyncMock(return_value=response)
    return client


@pytest.mark.asyncio
async def test_happy_path(db_session, test_user, make_trip) -> None:
    """Mock APNs success → NotificationLog created, trip updated."""
    trip = await make_trip(
        name="Push Test",
        arrival_hours_from_now=1.5,
        status=TripStatus.monitoring,
    )
    async with test_session_factory() as session:
        from sqlalchemy import update

        await session.execute(
            update(Trip)
            .where(Trip.id == trip.id)
            .values(last_eta_seconds=2700)
        )
        await session.commit()

    await _add_device_token(test_user.id, "token-happy")

    apns = _mock_apns_success()
    departure = datetime.now(timezone.utc) + timedelta(minutes=10)
    ctx = _build_ctx(apns_client=apns)

    await send_push_notification(
        ctx, str(trip.id), "prepare", departure.isoformat()
    )

    # APNs was called
    apns.send_notification.assert_called_once()

    # NotificationLog was created
    async with test_session_factory() as session:
        logs = (
            await session.execute(
                select(NotificationLog).where(
                    NotificationLog.trip_id == trip.id
                )
            )
        ).scalars().all()
        assert len(logs) == 1
        assert logs[0].delivery_status == DeliveryStatus.delivered
        assert logs[0].type == NotificationType.prepare
        assert logs[0].apns_id == "apns-uuid-123"

    # Trip notification_count incremented
    async with test_session_factory() as session:
        updated = (
            await session.execute(select(Trip).where(Trip.id == trip.id))
        ).scalar_one()
        assert updated.notification_count == 1
        assert updated.notified is True


@pytest.mark.asyncio
async def test_leave_now_transitions_to_departed(
    db_session, test_user, make_trip
) -> None:
    """tier=leave_now → trip.status=departed."""
    trip = await make_trip(
        name="Leave Now Push",
        arrival_hours_from_now=1.0,
        status=TripStatus.monitoring,
    )
    async with test_session_factory() as session:
        from sqlalchemy import update

        await session.execute(
            update(Trip)
            .where(Trip.id == trip.id)
            .values(last_eta_seconds=2700)
        )
        await session.commit()

    await _add_device_token(test_user.id, "token-leave-now")

    apns = _mock_apns_success()
    departure = datetime.now(timezone.utc)
    ctx = _build_ctx(apns_client=apns)

    await send_push_notification(
        ctx, str(trip.id), "leave_now", departure.isoformat()
    )

    # Trip status should be departed
    async with test_session_factory() as session:
        updated = (
            await session.execute(select(Trip).where(Trip.id == trip.id))
        ).scalar_one()
        assert updated.status == TripStatus.departed


@pytest.mark.asyncio
async def test_stale_token_deactivated(
    db_session, test_user, make_trip
) -> None:
    """APNs 'Unregistered' → token.is_active=False."""
    trip = await make_trip(
        name="Stale Token Test",
        arrival_hours_from_now=1.5,
        status=TripStatus.monitoring,
    )
    async with test_session_factory() as session:
        from sqlalchemy import update

        await session.execute(
            update(Trip)
            .where(Trip.id == trip.id)
            .values(last_eta_seconds=2700)
        )
        await session.commit()

    device_token = await _add_device_token(test_user.id, "token-stale")

    apns = _mock_apns_unregistered()
    departure = datetime.now(timezone.utc) + timedelta(minutes=10)
    ctx = _build_ctx(apns_client=apns)

    await send_push_notification(
        ctx, str(trip.id), "prepare", departure.isoformat()
    )

    # Token should be deactivated
    async with test_session_factory() as session:
        dt = (
            await session.execute(
                select(DeviceToken).where(DeviceToken.id == device_token.id)
            )
        ).scalar_one()
        assert dt.is_active is False


@pytest.mark.asyncio
async def test_no_tokens_bails(db_session, test_user, make_trip) -> None:
    """No device tokens → returns with NotificationLog (failed status)."""
    trip = await make_trip(
        name="No Tokens Trip",
        arrival_hours_from_now=1.5,
        status=TripStatus.monitoring,
    )
    async with test_session_factory() as session:
        from sqlalchemy import update

        await session.execute(
            update(Trip)
            .where(Trip.id == trip.id)
            .values(last_eta_seconds=2700)
        )
        await session.commit()

    # Don't add any device tokens
    apns = _mock_apns_success()
    departure = datetime.now(timezone.utc) + timedelta(minutes=10)
    ctx = _build_ctx(apns_client=apns)

    await send_push_notification(
        ctx, str(trip.id), "prepare", departure.isoformat()
    )

    # APNs should NOT have been called
    apns.send_notification.assert_not_called()

    # But a NotificationLog with failed status should exist (A4 fix)
    async with test_session_factory() as session:
        logs = (
            await session.execute(
                select(NotificationLog).where(
                    NotificationLog.trip_id == trip.id
                )
            )
        ).scalars().all()
        assert len(logs) == 1
        assert logs[0].delivery_status == DeliveryStatus.failed


@pytest.mark.asyncio
async def test_apns_not_configured(db_session, test_user, make_trip) -> None:
    """No apns_client in ctx → NotificationLog with failed status."""
    trip = await make_trip(
        name="No APNs Trip",
        arrival_hours_from_now=1.5,
        status=TripStatus.monitoring,
    )
    async with test_session_factory() as session:
        from sqlalchemy import update

        await session.execute(
            update(Trip)
            .where(Trip.id == trip.id)
            .values(last_eta_seconds=2700)
        )
        await session.commit()

    await _add_device_token(test_user.id, "token-no-apns")

    # No apns_client in context
    ctx = _build_ctx(apns_client=None)
    departure = datetime.now(timezone.utc) + timedelta(minutes=10)

    await send_push_notification(
        ctx, str(trip.id), "prepare", departure.isoformat()
    )

    # NotificationLog should exist with failed status
    async with test_session_factory() as session:
        logs = (
            await session.execute(
                select(NotificationLog).where(
                    NotificationLog.trip_id == trip.id
                )
            )
        ).scalars().all()
        assert len(logs) == 1
        assert logs[0].delivery_status == DeliveryStatus.failed
