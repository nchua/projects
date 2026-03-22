"""Traffic checker — the check_trip_eta ARQ job.

Loads a trip, checks the Redis ETA cache, calls the Apple MapKit Server API
if needed, stores an ETA snapshot, and enqueues alert evaluation.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, update

from app.models.enums import TripStatus
from app.models.trip import Trip
from app.models.trip_eta_snapshot import TripEtaSnapshot
from app.schemas.eta import EtaResult
from app.services.rate_limiter import (
    RateLimitExceeded,
    check_rate_limit,
    increment_cost_counter,
)
from app.models.enums import MonitoringPhase
from app.services.trip_scanner import determine_phase

logger = logging.getLogger(__name__)


def _cache_key(
    origin_lat: float, origin_lng: float,
    dest_lat: float, dest_lng: float,
) -> str:
    """Generate a Redis cache key for an ETA lookup.

    Rounds to 4 decimal places (~11m precision) for deduplication.
    """
    return (
        f"eta:{round(origin_lat, 4)}_{round(origin_lng, 4)}"
        f":{round(dest_lat, 4)}_{round(dest_lng, 4)}"
    )


def _compute_api_departure_time(trip: Trip) -> datetime | None:
    """Determine the departure time to send to the MapKit Server API.

    Uses the current recommended departure time (notify_at), not 'now'.
    Falls back to current time if notify_at is in the past.
    """
    now = datetime.now(timezone.utc)

    candidate = trip.notify_at
    if candidate is None and trip.last_eta_seconds is not None:
        candidate = (
            trip.arrival_time
            - timedelta(seconds=trip.last_eta_seconds)
            - timedelta(minutes=trip.buffer_minutes)
        )

    if candidate is None:
        return None  # Let MapKit use current traffic

    if candidate < now:
        return now  # Past notify_at — use current time

    if candidate > now + timedelta(hours=3):
        return None  # Too far ahead — omit for current conditions

    return candidate


async def check_trip_eta(ctx: dict[str, Any], trip_id: str) -> None:
    """ARQ job: check ETA for a single trip.

    Steps:
    1. Load trip from DB
    2. Check Redis ETA cache
    3. Call Apple MapKit Server API (if no cache hit)
    4. Store ETA snapshot
    5. Update trip record
    6. Enqueue evaluate_alert
    """
    now = datetime.now(timezone.utc)
    session_factory = ctx["db_session"]
    redis = ctx["redis"]
    routes_client = ctx["routes_client"]

    async with session_factory() as session:
        stmt = select(Trip).where(Trip.id == UUID(trip_id))
        result = await session.execute(stmt)
        trip = result.scalar_one_or_none()

    if trip is None:
        logger.warning(f"Trip {trip_id} not found — skipping")
        return

    if trip.status not in (TripStatus.pending, TripStatus.monitoring):
        logger.debug(f"Trip {trip_id} status is {trip.status} — skipping")
        return

    if trip.is_deleted:
        return

    cache_key = _cache_key(
        trip.origin_lat, trip.origin_lng,
        trip.dest_lat, trip.dest_lng,
    )
    cached = await redis.get(cache_key)

    eta_result: EtaResult | None = None

    if cached:
        try:
            data = json.loads(cached)
            phase = determine_phase(
                trip.arrival_time, trip.last_eta_seconds,
                trip.buffer_minutes, now,
            )
            # For critical phase, skip cache if older than 90s
            checked_at_str = data.get("checked_at", "")
            if checked_at_str:
                checked_at = datetime.fromisoformat(checked_at_str)
                age = (now - checked_at.replace(tzinfo=timezone.utc)).total_seconds()
                if phase == MonitoringPhase.critical and age > 90:
                    cached = None  # Force fresh check
                else:
                    eta_result = EtaResult.from_cache(data)
        except (json.JSONDecodeError, KeyError, ValueError):
            cached = None  # Invalid cache — fetch fresh

    if eta_result is None:
        try:
            await check_rate_limit(redis, str(trip.user_id))
        except RateLimitExceeded as e:
            logger.warning(f"Rate limit hit for trip {trip_id}: {e}")
            return  # Skip this check — will be retried next cycle

        departure_time = _compute_api_departure_time(trip)

        try:
            eta_result = await routes_client.compute_route(
                origin_lat=trip.origin_lat,
                origin_lng=trip.origin_lng,
                dest_lat=trip.dest_lat,
                dest_lng=trip.dest_lng,
                departure_time=departure_time,
            )
        except Exception:
            logger.exception(f"MapKit API error for trip {trip_id}")
            raise  # Let ARQ retry

        # Track API cost
        await increment_cost_counter(redis, provider="apple_mapkit")

        # Cache the result (TTL: 2 minutes)
        await redis.setex(
            cache_key, 120, json.dumps(eta_result.to_cache_dict())
        )

    async with session_factory() as session:
        snapshot = TripEtaSnapshot(
            trip_id=UUID(trip_id),
            duration_seconds=eta_result.duration_seconds,
            duration_in_traffic_seconds=eta_result.duration_in_traffic_seconds,
            congestion_level=eta_result.congestion_level,
            distance_meters=eta_result.distance_meters,
        )
        session.add(snapshot)

        new_notify_at = (
            trip.arrival_time
            - timedelta(seconds=eta_result.duration_in_traffic_seconds)
            - timedelta(minutes=trip.buffer_minutes)
        )

        update_values: dict[str, Any] = {
            "last_eta_seconds": eta_result.duration_in_traffic_seconds,
            "last_checked_at": now,
            "notify_at": new_notify_at,
            "updated_at": now,
        }

        # Set baseline duration on first check
        if trip.baseline_duration_seconds is None:
            update_values["baseline_duration_seconds"] = eta_result.duration_seconds

        await session.execute(
            update(Trip).where(Trip.id == UUID(trip_id)).values(**update_values)
        )
        await session.commit()

    await redis.enqueue_job(
        "_evaluate_alert",
        trip_id,
        eta_result.duration_in_traffic_seconds,
        _job_id=f"alert-{trip_id}-{now.strftime('%Y%m%d%H%M')}",
    )
