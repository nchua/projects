"""Trip scanner — the heartbeat of the notification engine.

The scan_active_trips cron runs every 60s, finds trips that need a
traffic check, and enqueues check_trip_eta jobs.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update

from app.models.enums import MonitoringPhase, TripStatus
from app.models.trip import Trip
from app.services.utils import haversine

logger = logging.getLogger(__name__)

# Phase polling intervals in seconds
PHASE_INTERVALS: dict[MonitoringPhase, int] = {
    MonitoringPhase.dormant: 0,       # Don't poll
    MonitoringPhase.passive: 900,     # 15 min
    MonitoringPhase.active: 300,      # 5 min
    MonitoringPhase.critical: 120,    # 2 min
    MonitoringPhase.departed: 0,      # Don't poll
}

# Average speed for rough ETA estimate (km/h)
ROUGH_AVG_SPEED_KMH = 40.0


def determine_phase(
    arrival_time: datetime,
    last_eta_seconds: int | None,
    buffer_minutes: int,
    now: datetime | None = None,
) -> MonitoringPhase:
    """Determine the monitoring phase for a trip.

    Uses the estimated notification time (arrival - ETA - buffer) to decide
    how aggressively to poll for traffic updates.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    if last_eta_seconds is not None:
        estimated_notify_at = (
            arrival_time
            - timedelta(seconds=last_eta_seconds)
            - timedelta(minutes=buffer_minutes)
        )
    else:
        # No ETA yet — assume 1 hour as rough default
        estimated_notify_at = arrival_time - timedelta(hours=1)

    time_until_notify = (estimated_notify_at - now).total_seconds()

    if time_until_notify > 3 * 3600:
        return MonitoringPhase.dormant
    if time_until_notify > 1 * 3600:
        return MonitoringPhase.passive
    if time_until_notify > 15 * 60:
        return MonitoringPhase.active
    if time_until_notify > 0:
        return MonitoringPhase.critical
    return MonitoringPhase.departed


def should_check_now(
    phase: MonitoringPhase,
    last_checked_at: datetime | None,
    now: datetime | None = None,
) -> bool:
    """Determine if a trip needs a traffic check right now.

    Based on the phase's polling interval and when the trip was last checked.
    """
    if phase in (MonitoringPhase.dormant, MonitoringPhase.departed):
        return False

    if last_checked_at is None:
        return True  # Never checked — always check

    if now is None:
        now = datetime.now(timezone.utc)

    interval = PHASE_INTERVALS[phase]
    elapsed = (now - last_checked_at).total_seconds()
    return elapsed >= interval


def estimate_rough_eta_seconds(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
) -> int:
    """Estimate rough ETA using straight-line distance / average speed."""
    distance_km = haversine(origin_lat, origin_lng, dest_lat, dest_lng)
    return int((distance_km / ROUGH_AVG_SPEED_KMH) * 3600)


async def scan_active_trips(ctx: dict[str, Any]) -> None:
    """Cron job: scan all active trips and enqueue ETA checks as needed.

    Runs every 60 seconds. Queries trips that are within the monitoring
    window, determines their phase, and enqueues check_trip_eta jobs.
    """
    now = datetime.now(timezone.utc)
    session_factory = ctx["db_session"]
    redis = ctx["redis"]

    async with session_factory() as session:
        # Query trips that are pending/monitoring with arrival in next 3.5 hours
        stmt = (
            select(Trip)
            .where(
                Trip.status.in_([TripStatus.pending, TripStatus.monitoring]),
                Trip.arrival_time > now,
                Trip.arrival_time < now + timedelta(hours=3, minutes=30),
                Trip.is_deleted.is_(False),
            )
            .order_by(Trip.arrival_time.asc())
        )
        result = await session.execute(stmt)
        trips = result.scalars().all()

    enqueued = 0
    for trip in trips:
        # For never-checked trips, estimate a rough ETA
        eta_seconds = trip.last_eta_seconds
        if eta_seconds is None:
            eta_seconds = estimate_rough_eta_seconds(
                trip.origin_lat, trip.origin_lng,
                trip.dest_lat, trip.dest_lng,
            )

        phase = determine_phase(
            arrival_time=trip.arrival_time,
            last_eta_seconds=eta_seconds,
            buffer_minutes=trip.buffer_minutes,
            now=now,
        )

        if not should_check_now(phase, trip.last_checked_at, now):
            continue

        # Transition from pending to monitoring on first check
        if trip.status == TripStatus.pending:
            async with session_factory() as session:
                await session.execute(
                    update(Trip)
                    .where(Trip.id == trip.id)
                    .values(
                        status=TripStatus.monitoring,
                        monitoring_started_at=now,
                    )
                )
                await session.commit()

        # Enqueue ETA check with dedup key
        timestamp_minute = now.strftime("%Y%m%d%H%M")
        await redis.enqueue_job(
            "_check_trip_eta",
            str(trip.id),
            _job_id=f"eta-{trip.id}-{timestamp_minute}",
        )
        enqueued += 1

    if enqueued > 0:
        logger.info(f"Enqueued {enqueued} ETA checks from {len(trips)} active trips")


async def cleanup_expired_trips(ctx: dict[str, Any]) -> None:
    """Cron job: mark expired trips as completed.

    Runs every hour. Trips whose arrival_time has passed and are still
    in monitoring status get transitioned to completed.
    """
    now = datetime.now(timezone.utc)
    session_factory = ctx["db_session"]

    async with session_factory() as session:
        # Trips past their arrival time by > 30 min, still monitoring
        cutoff = now - timedelta(minutes=30)
        stmt = (
            update(Trip)
            .where(
                Trip.status.in_([TripStatus.pending, TripStatus.monitoring]),
                Trip.arrival_time < cutoff,
                Trip.is_deleted.is_(False),
            )
            .values(status=TripStatus.completed, updated_at=now)
        )
        result = await session.execute(stmt)
        await session.commit()

        if result.rowcount > 0:
            logger.info(f"Marked {result.rowcount} expired trips as completed")
