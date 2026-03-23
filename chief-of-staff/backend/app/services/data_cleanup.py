"""Data cleanup cron job for the ARQ worker.

Per spec:
- Raw sync data purged after 7 days
- Action items auto-archive after 30 days if never acknowledged
- Audit logs cleaned per retention policy
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.action_item import ActionItem
from app.models.audit_log import AuditLog
from app.models.enums import ActionItemStatus

logger = logging.getLogger(__name__)

# Retention periods
AUDIT_LOG_RETENTION_DAYS = 90
ACTION_ITEM_ARCHIVE_DAYS = 30


async def cleanup_old_data(ctx: dict[str, Any]) -> None:
    """Run all cleanup tasks."""
    session_factory = ctx["db_session"]

    async with session_factory() as session:
        archived = await _archive_stale_action_items(session)
        purged = await _purge_old_audit_logs(session)
        await session.commit()

    logger.info(
        "Cleanup: archived %d action items, "
        "purged %d audit logs",
        archived,
        purged,
    )


async def _archive_stale_action_items(
    session: AsyncSession,
) -> int:
    """Auto-archive action items older than 30 days if never acknowledged."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(
        days=ACTION_ITEM_ARCHIVE_DAYS
    )

    result = await session.execute(
        update(ActionItem)
        .where(
            ActionItem.status == ActionItemStatus.NEW.value,
            ActionItem.created_at < cutoff,
        )
        .values(status=ActionItemStatus.DISMISSED.value)
    )
    return result.rowcount


async def _purge_old_audit_logs(
    session: AsyncSession,
) -> int:
    """Delete audit logs older than retention period."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(
        days=AUDIT_LOG_RETENTION_DAYS
    )

    result = await session.execute(
        delete(AuditLog).where(AuditLog.created_at < cutoff)
    )
    return result.rowcount
