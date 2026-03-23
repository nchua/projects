"""Briefing generation cron job for the ARQ worker.

Generates morning briefings for all users at their configured
briefing time (default 7am in their timezone).
"""

import logging
from datetime import date, datetime, time, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as SyncSession

from app.models.user import User

logger = logging.getLogger(__name__)


async def generate_morning_briefings(
    ctx: dict[str, Any],
) -> None:
    """Check all users and generate briefings for those at briefing time."""
    session_factory = ctx["db_session"]

    async with session_factory() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()

    now_utc = datetime.now(tz=timezone.utc)

    for user in users:
        if user.is_deleted:
            continue

        if not _is_briefing_time(user, now_utc):
            continue

        # Use sync session for briefing generation
        # (briefing_service uses sync SQLAlchemy)
        try:
            _generate_for_user(user.id, user.timezone)
            logger.info(
                "Generated briefing for user %s", user.id
            )
        except Exception:
            logger.exception(
                "Failed to generate briefing for user %s",
                user.id,
            )


def _generate_for_user(
    user_id: str, user_tz: str | None
) -> None:
    """Generate a briefing using the sync database session."""
    from app.core.database import SessionLocal
    from app.services.briefing_service import (
        generate_morning_briefing,
    )

    today = date.today()
    if user_tz:
        try:
            from zoneinfo import ZoneInfo
            today = datetime.now(
                tz=timezone.utc
            ).astimezone(ZoneInfo(user_tz)).date()
        except (KeyError, ImportError):
            pass

    db: SyncSession = SessionLocal()
    try:
        generate_morning_briefing(user_id, db, today)
        db.commit()
    finally:
        db.close()


def _is_briefing_time(
    user: User, now_utc: datetime
) -> bool:
    """Check if it's briefing time for this user (within 5-min window)."""
    # Default briefing at 7:00 AM user-local
    wake = time(7, 0)
    wake_str = getattr(user, "wake_time", None)
    if wake_str and isinstance(wake_str, str):
        parts = wake_str.split(":")
        wake = time(int(parts[0]), int(parts[1]))

    user_tz = getattr(user, "timezone", None)
    if user_tz:
        try:
            from zoneinfo import ZoneInfo
            local_now = now_utc.astimezone(ZoneInfo(user_tz))
        except (KeyError, ImportError):
            local_now = now_utc
    else:
        local_now = now_utc

    current = local_now.time()

    # Within a 5-minute window of wake time
    wake_minutes = wake.hour * 60 + wake.minute
    current_minutes = current.hour * 60 + current.minute
    return 0 <= (current_minutes - wake_minutes) < 5
