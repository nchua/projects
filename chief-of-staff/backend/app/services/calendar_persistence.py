"""Shared calendar event persistence — used by both manual sync and worker.

Extracted from app.api.integrations to avoid duplication between the
sync endpoint (sync Session) and the arq worker (async Session).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.models.calendar_event import CalendarEvent
from app.models.enums import IntegrationProvider

logger = logging.getLogger(__name__)

# Map IntegrationProvider value → CalendarProvider value
_PROVIDER_MAP = {
    IntegrationProvider.APPLE_CALENDAR.value: "apple",
    IntegrationProvider.GOOGLE_CALENDAR.value: "google",
}

CALENDAR_PROVIDERS = set(_PROVIDER_MAP.keys())


def persist_calendar_events(
    db: Session,
    user_id: str,
    provider: str,
    raw_items: list[dict[str, Any]],
) -> int:
    """Upsert CalendarEvent rows from sync results.

    Returns the number of events upserted.
    """
    cal_provider = _PROVIDER_MAP.get(provider)
    if not cal_provider:
        return 0

    now = datetime.now(tz=timezone.utc)
    count = 0

    for item in raw_items:
        # Extract external_id — Apple uses "apple_calendar:<uid>", Google uses "source_id"
        source_id = item.get("source_id", "")
        if source_id.startswith("apple_calendar:"):
            external_id = source_id.removeprefix("apple_calendar:")
        elif source_id.startswith("google_calendar:"):
            external_id = source_id.removeprefix("google_calendar:")
        else:
            external_id = source_id

        if not external_id:
            continue

        # Handle Google cancelled events
        if item.get("cancelled"):
            db.query(CalendarEvent).filter(
                CalendarEvent.user_id == user_id,
                CalendarEvent.provider == cal_provider,
                CalendarEvent.external_id == external_id,
            ).delete()
            continue

        # Parse start/end times — Apple uses "date"/"end_date", Google uses "start_time"/"end_time"
        start_raw = item.get("start_time") or item.get("date")
        end_raw = item.get("end_time") or item.get("end_date")

        if not start_raw or not end_raw:
            continue

        try:
            start_time = datetime.fromisoformat(str(start_raw))
            end_time = datetime.fromisoformat(str(end_raw))
        except (ValueError, TypeError):
            logger.warning("Skipping event with unparseable dates: %s", item.get("title"))
            continue

        is_all_day = item.get("is_all_day", False)

        # Upsert: find existing or create new
        existing = (
            db.query(CalendarEvent)
            .filter(
                CalendarEvent.user_id == user_id,
                CalendarEvent.provider == cal_provider,
                CalendarEvent.external_id == external_id,
            )
            .first()
        )

        if existing:
            existing.title = item.get("title", "(No title)")
            existing.description = item.get("notes") or item.get("body", "")
            existing.start_time = start_time
            existing.end_time = end_time
            existing.location = item.get("location", "")
            existing.is_all_day = is_all_day
            existing.calendar_id = item.get("calendar", "")
            existing.attendees = item.get("attendees")
            existing.synced_at = now
        else:
            event = CalendarEvent(
                user_id=user_id,
                provider=cal_provider,
                external_id=external_id,
                title=item.get("title", "(No title)"),
                description=item.get("notes") or item.get("body", ""),
                start_time=start_time,
                end_time=end_time,
                location=item.get("location", ""),
                is_all_day=is_all_day,
                calendar_id=item.get("calendar", ""),
                attendees=item.get("attendees"),
                synced_at=now,
            )
            db.add(event)

        count += 1

    return count


async def persist_calendar_events_async(
    session: AsyncSession,
    user_id: str,
    provider: str,
    raw_items: list[dict[str, Any]],
) -> int:
    """Async version for the arq worker (AsyncSession).

    Returns the number of events upserted.
    """
    from sqlalchemy import select, delete

    cal_provider = _PROVIDER_MAP.get(provider)
    if not cal_provider:
        return 0

    now = datetime.now(tz=timezone.utc)
    count = 0

    for item in raw_items:
        source_id = item.get("source_id", "")
        if source_id.startswith("apple_calendar:"):
            external_id = source_id.removeprefix("apple_calendar:")
        elif source_id.startswith("google_calendar:"):
            external_id = source_id.removeprefix("google_calendar:")
        else:
            external_id = source_id

        if not external_id:
            continue

        if item.get("cancelled"):
            await session.execute(
                delete(CalendarEvent).where(
                    CalendarEvent.user_id == user_id,
                    CalendarEvent.provider == cal_provider,
                    CalendarEvent.external_id == external_id,
                )
            )
            continue

        start_raw = item.get("start_time") or item.get("date")
        end_raw = item.get("end_time") or item.get("end_date")

        if not start_raw or not end_raw:
            continue

        try:
            start_time = datetime.fromisoformat(str(start_raw))
            end_time = datetime.fromisoformat(str(end_raw))
        except (ValueError, TypeError):
            logger.warning("Skipping event with unparseable dates: %s", item.get("title"))
            continue

        is_all_day = item.get("is_all_day", False)

        result = await session.execute(
            select(CalendarEvent).where(
                CalendarEvent.user_id == user_id,
                CalendarEvent.provider == cal_provider,
                CalendarEvent.external_id == external_id,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.title = item.get("title", "(No title)")
            existing.description = item.get("notes") or item.get("body", "")
            existing.start_time = start_time
            existing.end_time = end_time
            existing.location = item.get("location", "")
            existing.is_all_day = is_all_day
            existing.calendar_id = item.get("calendar", "")
            existing.attendees = item.get("attendees")
            existing.synced_at = now
        else:
            event = CalendarEvent(
                user_id=user_id,
                provider=cal_provider,
                external_id=external_id,
                title=item.get("title", "(No title)"),
                description=item.get("notes") or item.get("body", ""),
                start_time=start_time,
                end_time=end_time,
                location=item.get("location", ""),
                is_all_day=is_all_day,
                calendar_id=item.get("calendar", ""),
                attendees=item.get("attendees"),
                synced_at=now,
            )
            session.add(event)

        count += 1

    return count
