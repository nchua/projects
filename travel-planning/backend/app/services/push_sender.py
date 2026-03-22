"""Push notification sender — builds and dispatches FCM messages.

Handles notification content generation for all 5 tiers, per-tier APNs
configuration, multi-device delivery, and notification logging.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, update

from app.models.device_token import DeviceToken
from app.models.enums import DeliveryStatus, NotificationType, TripStatus
from app.models.notification_log import NotificationLog
from app.models.trip import Trip
from app.models.user import User

logger = logging.getLogger(__name__)

# Per-tier APNs configuration
TIER_APNS_CONFIG: dict[str, dict[str, Any]] = {
    "heads_up": {
        "priority": "5",  # Silent
        "interruption_level": "passive",
        "sound": None,
        "relevance_score": 0.3,
    },
    "prepare": {
        "priority": "10",
        "interruption_level": "active",
        "sound": "default",
        "relevance_score": 0.6,
    },
    "leave_soon": {
        "priority": "10",
        "interruption_level": "time-sensitive",
        "sound": "departure_alert.caf",
        "relevance_score": 0.9,
    },
    "leave_now": {
        "priority": "10",
        "interruption_level": "time-sensitive",  # Upgrade to critical once entitled
        "sound": "critical_departure.caf",
        "relevance_score": 1.0,
    },
    "running_late": {
        "priority": "10",
        "interruption_level": "active",
        "sound": "default",
        "relevance_score": 0.7,
    },
}


def _resolve_timezone(tz_name: str) -> Any:
    """Resolve a timezone name to a pytz timezone object."""
    try:
        import pytz

        return pytz.timezone(tz_name)
    except Exception:
        return timezone.utc


def _format_time(dt: datetime, tz: Any) -> str:
    """Format a datetime in the given timezone as '2:15 PM'."""
    local_dt = dt.astimezone(tz)
    return local_dt.strftime("%-I:%M %p")


def _minutes_until(target: datetime) -> int:
    """Minutes from now until a target datetime."""
    delta = (target - datetime.now(timezone.utc)).total_seconds()
    return max(0, round(delta / 60))


def build_notification(
    trip: Trip,
    user: User,
    tier: str,
    departure_time: datetime,
    change_direction: str,
) -> tuple[str, str]:
    """Build notification title and body for a given tier.

    Returns (title, body) tuple.
    """
    tz = _resolve_timezone(user.timezone or "America/Los_Angeles")
    departure_str = _format_time(departure_time, tz)
    arrival_str = _format_time(trip.arrival_time, tz)
    dest_name = (
        trip.name or trip.dest_address[:30]
        if trip.dest_address
        else "destination"
    )
    eta_minutes = round((trip.last_eta_seconds or 0) / 60)

    if tier == "heads_up":
        mins = _minutes_until(trip.arrival_time)
        title = f"{dest_name} in {mins} min"
        body = f"Light traffic. Plan to leave by {departure_str}."

    elif tier == "prepare":
        if change_direction == "worse":
            title = f"Leave earlier for {dest_name}"
            body = (
                f"Traffic building. Leave by {departure_str} "
                f"for your {arrival_str} arrival. ({eta_minutes} min drive)"
            )
        elif change_direction == "better":
            title = f"Traffic cleared for {dest_name}"
            body = f"You can leave at {departure_str}. {eta_minutes} min drive."
        else:
            title = f"Leave by {departure_str}"
            body = f"{eta_minutes} min drive to {dest_name}. Arrive by {arrival_str}."

    elif tier == "leave_soon":
        title = f"Leave soon for {dest_name}"
        body = (
            f"Leave by {departure_str} to arrive by {arrival_str}. "
            f"{eta_minutes} min with current traffic."
        )

    elif tier == "leave_now":
        title = "Time to leave!"
        body = (
            f"Leave now for {dest_name}. "
            f"{eta_minutes} min drive to arrive by {arrival_str}."
        )

    elif tier == "running_late":
        now = datetime.now(timezone.utc)
        minutes_late = max(0, round((now - departure_time).total_seconds() / 60))
        estimated_arrival = now + timedelta(seconds=trip.last_eta_seconds or 0)
        eta_str = _format_time(estimated_arrival, tz)
        title = f"Running late for {dest_name}"
        body = (
            f"You're {minutes_late} min behind. "
            f"Current ETA: {eta_str}. Navigate now?"
        )

    else:
        title = f"Trip update for {dest_name}"
        body = f"Leave by {departure_str} to arrive by {arrival_str}."

    return title, body


def build_fcm_payload(
    token: str,
    trip: Trip,
    tier: str,
    title: str,
    body: str,
    departure_time: datetime,
    silent: bool = False,
) -> dict[str, Any]:
    """Build a complete FCM message payload with APNs config."""
    apns_config = TIER_APNS_CONFIG.get(tier, TIER_APNS_CONFIG["prepare"])

    # Data payload (always delivered, even for silent pushes)
    data_payload = {
        "trip_id": str(trip.id),
        "tier": tier,
        "recommended_departure": departure_time.isoformat(),
        "eta_seconds": str(trip.last_eta_seconds or 0),
        "arrival_time": trip.arrival_time.isoformat(),
        "dest_lat": str(trip.dest_lat),
        "dest_lng": str(trip.dest_lng),
        "deep_link": f"depart://trip/{trip.id}",
    }

    # APNs payload
    aps: dict[str, Any] = {
        "badge": 1,
        "category": "TRIP_ALERT",
        "thread-id": f"trip-{trip.id}",
        "interruption-level": apns_config["interruption_level"],
        "relevance-score": apns_config["relevance_score"],
        "mutable-content": 1,
    }

    if not silent and apns_config["sound"]:
        aps["sound"] = apns_config["sound"]
        aps["alert"] = {"title": title, "body": body}
    elif silent:
        aps["content-available"] = 1
    else:
        aps["alert"] = {"title": title, "body": body}

    return {
        "token": token,
        "title": title,
        "body": body,
        "data": data_payload,
        "apns": {
            "headers": {
                "apns-priority": apns_config["priority"],
                "apns-push-type": "alert" if not silent else "background",
            },
            "payload": {"aps": aps},
        },
    }


async def send_push_notification(
    ctx: dict[str, Any],
    trip_id: str,
    tier: str,
    departure_time_iso: str,
    silent: bool = False,
    change_direction: str = "initial",
) -> None:
    """ARQ job: send a push notification for a trip.

    Steps:
    1. Load trip + user
    2. Build notification content
    3. Fetch device tokens
    4. Send via FCM
    5. Log the notification
    6. Update trip status for leave_now/running_late
    """
    session_factory = ctx["db_session"]

    departure_time = (
        datetime.fromisoformat(departure_time_iso)
        if departure_time_iso
        else datetime.now(timezone.utc)
    )

    # Step 1: Load trip + user
    async with session_factory() as session:
        trip_result = await session.execute(
            select(Trip).where(Trip.id == UUID(trip_id))
        )
        trip = trip_result.scalar_one_or_none()
        if trip is None:
            return

        user_result = await session.execute(
            select(User).where(User.id == trip.user_id)
        )
        user = user_result.scalar_one_or_none()
        if user is None:
            return

        # Step 2: Build notification content
        title, body = build_notification(
            trip, user, tier, departure_time, change_direction
        )

        # Step 3: Fetch active device tokens
        token_result = await session.execute(
            select(DeviceToken).where(
                DeviceToken.user_id == trip.user_id,
                DeviceToken.is_active.is_(True),
            )
        )
        tokens = token_result.scalars().all()

    if not tokens:
        logger.warning(f"No active device tokens for trip {trip_id}")
        return

    results = []
    fcm_message_id = None
    stale_token_ids: list[UUID] = []

    try:
        from firebase_admin import messaging

        for device_token in tokens:
            payload = build_fcm_payload(
                token=device_token.token,
                trip=trip,
                tier=tier,
                title=title,
                body=body,
                departure_time=departure_time,
                silent=silent,
            )

            message = messaging.Message(
                token=device_token.token,
                notification=messaging.Notification(
                    title=title, body=body
                )
                if not silent
                else None,
                data=payload["data"],
                apns=messaging.APNSConfig(
                    headers=payload["apns"]["headers"],
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            badge=1,
                            sound=payload["apns"]["payload"]["aps"].get(
                                "sound"
                            ),
                            category="TRIP_ALERT",
                            thread_id=f"trip-{trip.id}",
                            mutable_content=True,
                            content_available=silent,
                        )
                    ),
                ),
            )

            try:
                response = messaging.send(message)
                fcm_message_id = response
                results.append({"success": True, "id": response})
            except messaging.UnregisteredError:
                logger.info(
                    f"Token {device_token.token[:20]}... stale"
                )
                stale_token_ids.append(device_token.id)
            except messaging.QuotaExceededError:
                from arq import Retry

                raise Retry(defer=30)
            except Exception as e:
                logger.error(f"FCM send error: {e}")
                results.append({"success": False, "error": str(e)})
    except ImportError:
        logger.warning(
            "Firebase Admin SDK not available — skipping FCM send"
        )
        results.append({"success": False, "error": "Firebase not configured"})

    # Batch-deactivate stale tokens
    if stale_token_ids:
        async with session_factory() as session:
            await session.execute(
                update(DeviceToken)
                .where(DeviceToken.id.in_(stale_token_ids))
                .values(is_active=False)
            )
            await session.commit()

    # Step 5: Log the notification
    delivery_status = (
        DeliveryStatus.delivered
        if any(r.get("success") for r in results)
        else DeliveryStatus.failed
    )

    async with session_factory() as session:
        notification_type = NotificationType(tier)
        log_entry = NotificationLog(
            trip_id=UUID(trip_id),
            user_id=trip.user_id,
            type=notification_type,
            title=title,
            body=body,
            eta_at_send_seconds=trip.last_eta_seconds,
            recommended_departure=departure_time,
            delivery_status=delivery_status,
            fcm_message_id=fcm_message_id,
        )
        session.add(log_entry)

        # Step 6: Update trip status
        update_values: dict[str, Any] = {
            "notified": True,
            "notification_count": trip.notification_count + 1,
            "updated_at": datetime.now(timezone.utc),
        }

        if notification_type in (
            NotificationType.leave_now,
            NotificationType.running_late,
        ):
            update_values["status"] = TripStatus.departed

        await session.execute(
            update(Trip).where(Trip.id == UUID(trip_id)).values(**update_values)
        )
        await session.commit()

    logger.info(
        f"Trip {trip_id}: sent {tier} notification — "
        f"{sum(1 for r in results if r.get('success'))}/{len(results)} delivered"
    )
