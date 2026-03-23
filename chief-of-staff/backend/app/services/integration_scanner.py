"""Integration scanner — cron job that polls integrations on schedule.

Phase-based polling: aggressive (every 5 min) during active hours,
dormant overnight. Per-integration rate limiting with degraded mode.
"""

import logging
from datetime import datetime, time, timezone
from typing import Any

from sqlalchemy import select

from app.models.enums import IntegrationProvider
from app.models.integration import Integration
from app.models.sync_state import SyncState
from app.models.user import User

logger = logging.getLogger(__name__)


async def scan_integrations(ctx: dict[str, Any]) -> None:
    """Scan all active integrations and enqueue sync jobs.

    Only syncs during the user's active hours (between
    wake_time and sleep_time).
    """
    session_factory = ctx["db_session"]

    async with session_factory() as session:
        result = await session.execute(
            select(Integration, User)
            .join(User, Integration.user_id == User.id)
            .where(
                Integration.is_active.is_(True),
                Integration.status != "disabled",
            )
        )
        rows = result.all()

    now_utc = datetime.now(tz=timezone.utc)

    for integration, user in rows:
        if not _is_active_hours(user, now_utc):
            continue

        if _is_rate_limited(integration, now_utc):
            continue

        # Enqueue sync job
        from arq.connections import ArqRedis
        pool: ArqRedis = ctx["redis"]
        await pool.enqueue_job(
            "_sync_integration", integration.id
        )
        logger.debug(
            "Enqueued sync for %s (%s)",
            integration.provider,
            integration.id,
        )


async def sync_integration(
    ctx: dict[str, Any], integration_id: str
) -> None:
    """Sync a single integration: fetch data, update cursor."""
    from app.services.connectors.github import GitHubConnector
    from app.services.connectors.gmail import GmailConnector
    from app.services.connectors.google_calendar import (
        GoogleCalendarConnector,
    )
    from app.services.connectors.slack import SlackConnector
    from app.services.connectors.granola import GranolaConnector
    from app.services.connectors.apple_calendar import AppleCalendarConnector

    session_factory = ctx["db_session"]

    async with session_factory() as session:
        integration = await session.get(
            Integration, integration_id
        )
        if not integration or not integration.is_active:
            return

        # Get or create sync state
        result = await session.execute(
            select(SyncState).where(
                SyncState.integration_id == integration_id,
            )
        )
        sync_state = result.scalar_one_or_none()

        # Pick the right connector
        connector_map = {
            IntegrationProvider.GOOGLE_CALENDAR.value: GoogleCalendarConnector,
            IntegrationProvider.GMAIL.value: GmailConnector,
            IntegrationProvider.GITHUB.value: GitHubConnector,
            IntegrationProvider.SLACK.value: SlackConnector,
            IntegrationProvider.GRANOLA.value: GranolaConnector,
            IntegrationProvider.APPLE_CALENDAR.value: AppleCalendarConnector,
        }
        connector_cls = connector_map.get(integration.provider)
        if not connector_cls:
            logger.warning(
                "No connector for %s", integration.provider
            )
            return

        connector = connector_cls(integration)

        try:
            sync_result = await connector.sync(sync_state)

            # Update cursor
            if sync_result.new_cursor:
                if sync_state:
                    sync_state.cursor_value = (
                        sync_result.new_cursor
                    )
                    sync_state.last_sync_status = "success"
                    sync_state.last_sync_error = None
                else:
                    resource_type = _provider_resource_type(
                        integration.provider
                    )
                    sync_state = SyncState(
                        integration_id=integration_id,
                        resource_type=resource_type,
                        cursor_value=sync_result.new_cursor,
                        cursor_type="sync_token",
                        last_sync_status="success",
                    )
                    session.add(sync_state)

            integration.last_synced_at = datetime.now(
                tz=timezone.utc
            )

            # Enqueue message processing for providers with raw items
            if (
                sync_result.raw_items
                and integration.provider
                in (
                    IntegrationProvider.GMAIL.value,
                    IntegrationProvider.GITHUB.value,
                    IntegrationProvider.SLACK.value,
                    IntegrationProvider.GRANOLA.value,
                )
            ):
                from arq.connections import ArqRedis
                pool: ArqRedis = ctx["redis"]
                await pool.enqueue_job(
                    "_process_new_messages",
                    integration_id,
                    integration.user_id,
                    sync_result.raw_items,
                )

            if sync_result.errors:
                logger.warning(
                    "Sync %s had errors: %s",
                    integration.provider,
                    sync_result.errors,
                )

            await session.commit()

        except Exception as e:
            logger.error(
                "Sync failed for %s: %s",
                integration.provider, e,
            )
            integration.error_count += 1
            integration.last_error = str(e)[:500]
            if integration.error_count >= 3:
                integration.status = "failed"
            else:
                integration.status = "degraded"
            await session.commit()

        finally:
            await connector.close()


def _is_active_hours(user: User, now_utc: datetime) -> bool:
    """Check if it's within the user's active hours."""
    wake = _parse_time(
        getattr(user, "wake_time", None), default=time(7, 0)
    )
    sleep = _parse_time(
        getattr(user, "sleep_time", None), default=time(23, 0)
    )

    # Convert UTC to user's local time
    user_tz = getattr(user, "timezone", None)
    if user_tz:
        try:
            from zoneinfo import ZoneInfo
            local_now = now_utc.astimezone(ZoneInfo(user_tz))
            current_time = local_now.time()
        except (KeyError, ImportError):
            current_time = now_utc.time()
    else:
        current_time = now_utc.time()

    return wake <= current_time <= sleep


def _parse_time(value: Any, default: time) -> time:
    """Parse a time value from string or time object."""
    if value is None:
        return default
    if isinstance(value, time):
        return value
    if isinstance(value, str):
        parts = value.split(":")
        return time(int(parts[0]), int(parts[1]))
    return default


def _is_rate_limited(
    integration: Integration, now_utc: datetime
) -> bool:
    """Check if the integration is currently rate limited."""
    if (
        integration.rate_limit_remaining is not None
        and integration.rate_limit_remaining <= 0
        and integration.rate_limit_reset_at
        and integration.rate_limit_reset_at > now_utc
    ):
        return True
    return False


def _provider_resource_type(provider: str) -> str:
    """Map provider to default resource type for SyncState."""
    mapping = {
        IntegrationProvider.GOOGLE_CALENDAR.value: "calendar",
        IntegrationProvider.GMAIL.value: "inbox",
        IntegrationProvider.GITHUB.value: "notifications",
        IntegrationProvider.SLACK.value: "channels",
        IntegrationProvider.GRANOLA.value: "meetings",
    }
    return mapping.get(provider, "unknown")
