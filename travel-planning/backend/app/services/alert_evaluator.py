"""Alert evaluator — decides whether and what notification to send.

This is the most critical decision logic in the system. It takes a
trip's updated ETA and determines whether to send a notification,
and if so, what kind.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.models.enums import DeliveryStatus, NotificationType
from app.models.notification_log import NotificationLog
from app.models.trip import Trip
from app.models.user import User

logger = logging.getLogger(__name__)


@dataclass
class AlertDecision:
    """Result of alert evaluation."""

    should_send: bool
    tier: NotificationType | None = None
    departure_time: datetime | None = None
    silent: bool = False
    change_direction: str = "initial"
    reason: str = ""


def determine_alert_tier(time_until_departure_seconds: float) -> NotificationType:
    """Map time-until-departure to a notification tier.

    Args:
        time_until_departure_seconds: Seconds until the recommended
            departure time. Negative means departure time has passed.
    """
    minutes = time_until_departure_seconds / 60

    if minutes > 60:
        return NotificationType.heads_up
    if minutes > 15:
        return NotificationType.prepare
    if minutes > 5:
        return NotificationType.leave_soon
    if minutes > -5:
        return NotificationType.leave_now
    return NotificationType.running_late


def is_significant_change(
    new_eta: int,
    last_notified_eta: int | None,
    baseline_duration: int | None,
) -> bool:
    """Check if the ETA has changed enough to warrant a notification.

    Uses max(5 minutes, 10% of baseline trip duration) as the threshold.
    """
    if last_notified_eta is None:
        return True  # First notification always fires

    delta = abs(new_eta - last_notified_eta)
    baseline = baseline_duration or new_eta  # Fallback if no baseline stored
    threshold = max(300, baseline * 0.10)  # 5 min or 10%

    return delta >= threshold


def get_change_direction(
    new_eta: int, last_notified_eta: int | None
) -> str:
    """Determine if traffic got worse or better."""
    if last_notified_eta is None:
        return "initial"
    if new_eta > last_notified_eta:
        return "worse"
    return "better"


def passes_anti_spam(
    notifications_sent: list[NotificationLog],
    current_tier: NotificationType,
) -> bool | str:
    """Check anti-spam rules. Returns True, False, or 'silent_only'.

    Rules:
    1. Max 4 update notifications per trip (prepare/leave_soon only)
    2. Min 10 minutes between updates (leave_now/running_late exempt)
    3. If user dismissed 2+ alerts, downgrade to silent
    """
    now = datetime.now(timezone.utc)

    # Rule 1: Max 4 updates
    update_types = {NotificationType.prepare, NotificationType.leave_soon}
    update_count = sum(
        1 for n in notifications_sent if n.type in update_types
    )
    if update_count >= 4 and current_tier in update_types:
        return False

    # Rule 2: Min 10 minutes between updates
    if notifications_sent:
        last_sent = max(n.sent_at for n in notifications_sent)
        if last_sent.tzinfo is None:
            last_sent = last_sent.replace(tzinfo=timezone.utc)
        elapsed = (now - last_sent).total_seconds()
        if elapsed < 600:  # 10 minutes
            # leave_now and running_late bypass the cooldown
            if current_tier not in (
                NotificationType.leave_now,
                NotificationType.running_late,
            ):
                return False

    # Rule 3: Dismissed alerts -> silent only
    dismissed_count = sum(
        1 for n in notifications_sent
        if n.delivery_status == DeliveryStatus.dismissed
    )
    if dismissed_count >= 2 and current_tier not in (
        NotificationType.leave_now,
        NotificationType.running_late,
    ):
        return "silent_only"

    return True


def is_quiet_hours(user: User) -> bool:
    """Check if the current time falls within the user's quiet hours.

    Handles overnight quiet hours (e.g., 11 PM to 7 AM).
    """
    if user.quiet_hours_start is None or user.quiet_hours_end is None:
        return False

    try:
        import pytz

        tz = pytz.timezone(user.timezone)
        user_local_time = datetime.now(tz).time()
    except Exception:
        user_local_time = datetime.now(timezone.utc).time()

    start = user.quiet_hours_start
    end = user.quiet_hours_end

    # Handle overnight quiet hours (e.g., 23:00 to 07:00)
    if start > end:
        return user_local_time >= start or user_local_time < end
    return start <= user_local_time < end


def _already_sent_tier(
    tier: NotificationType, notifications: list[NotificationLog]
) -> bool:
    """Check if a notification of the given tier was already sent."""
    return any(n.type == tier for n in notifications)


def _get_last_notified_eta(
    notifications: list[NotificationLog],
) -> int | None:
    """Get the ETA that was recorded when the last notification was sent."""
    if not notifications:
        return None
    latest = max(notifications, key=lambda n: n.sent_at)
    return latest.eta_at_send_seconds


def evaluate_decision(
    trip: Trip,
    user: User,
    new_eta_seconds: int,
    notifications_sent: list[NotificationLog],
) -> AlertDecision:
    """Core decision logic — pure function for testability.

    Determines whether to send a notification and what kind.
    """
    now = datetime.now(timezone.utc)

    # Compute recommended departure time
    recommended_departure = (
        trip.arrival_time
        - timedelta(seconds=new_eta_seconds)
        - timedelta(minutes=trip.buffer_minutes)
    )
    time_until_departure = (recommended_departure - now).total_seconds()

    tier = determine_alert_tier(time_until_departure)
    last_notified_eta = _get_last_notified_eta(notifications_sent)
    change_direction = get_change_direction(new_eta_seconds, last_notified_eta)

    # ALWAYS send leave_now when time is up (once)
    if tier == NotificationType.leave_now and not _already_sent_tier(
        NotificationType.leave_now, notifications_sent
    ):
        return AlertDecision(
            should_send=True,
            tier=tier,
            departure_time=recommended_departure,
            change_direction=change_direction,
            reason="Time to leave",
        )

    # ALWAYS send running_late (once)
    if tier == NotificationType.running_late and not _already_sent_tier(
        NotificationType.running_late, notifications_sent
    ):
        return AlertDecision(
            should_send=True,
            tier=tier,
            departure_time=recommended_departure,
            change_direction=change_direction,
            reason="Past departure time",
        )

    # Send heads_up once when entering active monitoring
    if tier == NotificationType.heads_up and not _already_sent_tier(
        NotificationType.heads_up, notifications_sent
    ):
        return AlertDecision(
            should_send=True,
            tier=tier,
            departure_time=recommended_departure,
            silent=True,  # heads_up is always silent
            change_direction=change_direction,
            reason="Entering monitoring",
        )

    # For prepare / leave_soon: check significance + anti-spam
    if tier in (NotificationType.prepare, NotificationType.leave_soon):
        if not is_significant_change(
            new_eta_seconds, last_notified_eta, trip.baseline_duration_seconds
        ):
            return AlertDecision(
                should_send=False,
                reason="ETA change below significance threshold",
            )

        spam_check = passes_anti_spam(notifications_sent, tier)
        if spam_check is False:
            return AlertDecision(
                should_send=False, reason="Anti-spam rule triggered"
            )

        if is_quiet_hours(user) and tier != NotificationType.leave_soon:
            return AlertDecision(
                should_send=False, reason="Quiet hours active"
            )

        silent = spam_check == "silent_only"
        return AlertDecision(
            should_send=True,
            tier=tier,
            departure_time=recommended_departure,
            silent=silent,
            change_direction=change_direction,
            reason="Significant ETA change",
        )

    return AlertDecision(should_send=False, reason="No alert condition met")


async def evaluate_alert(
    ctx: dict[str, Any], trip_id: str, new_eta_seconds: int
) -> None:
    """ARQ job: evaluate whether to send a notification for a trip."""
    session_factory = ctx["db_session"]
    redis = ctx["redis"]

    async with session_factory() as session:
        # Load trip + user
        stmt = select(Trip).where(Trip.id == UUID(trip_id))
        result = await session.execute(stmt)
        trip = result.scalar_one_or_none()
        if trip is None:
            return

        user_stmt = select(User).where(User.id == trip.user_id)
        user_result = await session.execute(user_stmt)
        user = user_result.scalar_one_or_none()
        if user is None:
            return

        # Load notification history for this trip
        notif_stmt = (
            select(NotificationLog)
            .where(NotificationLog.trip_id == UUID(trip_id))
            .order_by(NotificationLog.sent_at.asc())
        )
        notif_result = await session.execute(notif_stmt)
        notifications_sent = list(notif_result.scalars().all())

    # Run the decision logic
    decision = evaluate_decision(trip, user, new_eta_seconds, notifications_sent)

    if not decision.should_send:
        logger.debug(
            f"Trip {trip_id}: no alert — {decision.reason}"
        )
        return

    logger.info(
        f"Trip {trip_id}: sending {decision.tier.value} alert "
        f"(direction: {decision.change_direction})"
    )

    # Enqueue the notification send
    departure_iso = (
        decision.departure_time.isoformat() if decision.departure_time else ""
    )
    await redis.enqueue_job(
        "_send_push_notification",
        trip_id,
        decision.tier.value,
        departure_iso,
        decision.silent,
        decision.change_direction,
    )
