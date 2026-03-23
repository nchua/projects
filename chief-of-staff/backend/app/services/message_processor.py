"""Message processor — worker job for AI extraction pipeline.

Takes raw messages from connector sync results and runs
the two-tier AI extraction (Haiku triage → Sonnet extraction).
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    ActionItemPriority,
    ActionItemSource,
    ActionItemStatus,
)
from app.models.action_item import ActionItem
from app.services.email_preprocessor import (
    hash_content,
    preprocess_body,
)
from app.services.extraction_service import (
    extract_action_items,
    triage_message,
)

logger = logging.getLogger(__name__)

MIN_BODY_CHARS = 50


async def process_new_messages(
    ctx: dict[str, Any],
    integration_id: str,
    user_id: str,
    messages: list[dict[str, Any]],
) -> None:
    """Process raw messages through the AI extraction pipeline.

    For Gmail: preprocess → dedup → triage (Haiku) → extract (Sonnet) → persist.
    For GitHub: structured extraction (no AI needed).
    """
    session_factory = ctx["db_session"]

    # Determine source from the first message
    if not messages:
        return

    first = messages[0]
    is_github = "action_type" in first

    async with session_factory() as session:
        if is_github:
            await _process_github(
                session, user_id, messages
            )
        else:
            await _process_gmail(
                session, user_id, messages
            )
        await session.commit()

    logger.info(
        "Processed %d messages for user %s",
        len(messages),
        user_id,
    )


async def _process_gmail(
    session: AsyncSession,
    user_id: str,
    messages: list[dict[str, Any]],
) -> None:
    """Process Gmail messages through AI extraction."""
    from sqlalchemy import select

    for msg in messages:
        body = msg.get("body", "")
        source_id = msg.get("source_id", "")

        processed_body = preprocess_body(body)
        if len(processed_body) < MIN_BODY_CHARS:
            continue

        # Dedup check
        content_hash = hash_content(
            f"{source_id}:{processed_body[:500]}"
        )
        result = await session.execute(
            select(ActionItem).where(
                ActionItem.dedup_hash == content_hash,
                ActionItem.user_id == user_id,
            )
        )
        if result.scalar_one_or_none():
            continue

        # Triage
        should_extract = await triage_message(
            processed_body,
            "gmail",
            msg.get("subject", ""),
            msg.get("sender", ""),
        )
        if not should_extract:
            continue

        # Extract
        extracted = await extract_action_items(
            processed_body,
            source="gmail",
            source_id=source_id,
            source_url=msg.get("source_url", ""),
            subject=msg.get("subject", ""),
            sender=msg.get("sender", ""),
        )

        # Persist
        for item_data in extracted:
            dedup = item_data.get("dedup_hash")
            if dedup:
                dup_result = await session.execute(
                    select(ActionItem).where(
                        ActionItem.dedup_hash == dedup,
                        ActionItem.user_id == user_id,
                    )
                )
                if dup_result.scalar_one_or_none():
                    continue

            action_item = ActionItem(
                user_id=user_id,
                source=ActionItemSource.GMAIL.value,
                source_id=item_data.get("source_id"),
                source_url=item_data.get("source_url"),
                title=item_data["title"],
                description=item_data.get("description"),
                confidence_score=item_data.get(
                    "confidence_score"
                ),
                priority=item_data.get(
                    "priority",
                    ActionItemPriority.MEDIUM.value,
                ),
                status=ActionItemStatus.NEW.value,
                dedup_hash=dedup,
            )
            session.add(action_item)


async def _process_github(
    session: AsyncSession,
    user_id: str,
    notifications: list[dict[str, Any]],
) -> None:
    """Process GitHub notifications into action items.

    Uses structured data — no AI needed.
    """
    from sqlalchemy import select

    actionable_types = {
        "pr_review_requested",
        "issue_assigned",
        "ci_failure",
        "mentioned",
    }

    priority_map = {
        "pr_review_requested": ActionItemPriority.MEDIUM.value,
        "issue_assigned": ActionItemPriority.MEDIUM.value,
        "ci_failure": ActionItemPriority.HIGH.value,
        "mentioned": ActionItemPriority.LOW.value,
    }
    confidence_map = {
        "pr_review_requested": 0.95,
        "issue_assigned": 0.95,
        "ci_failure": 0.90,
        "mentioned": 0.70,
    }
    title_prefix_map = {
        "pr_review_requested": "Review PR",
        "issue_assigned": "Resolve issue",
        "ci_failure": "Fix CI failure",
        "mentioned": "Respond to mention",
    }

    for notif in notifications:
        action_type = notif.get("action_type", "other")
        if action_type not in actionable_types:
            continue

        source_id = notif.get("source_id", "")
        dedup = hash_content(f"github:{source_id}")

        result = await session.execute(
            select(ActionItem).where(
                ActionItem.dedup_hash == dedup,
                ActionItem.user_id == user_id,
            )
        )
        if result.scalar_one_or_none():
            continue

        title = notif.get("title", "(No title)")
        prefix = title_prefix_map.get(action_type, "")
        full_title = (
            f"{prefix}: {title}" if prefix else title
        )[:200]
        repo = notif.get("repository", "")

        action_item = ActionItem(
            user_id=user_id,
            source=ActionItemSource.GITHUB.value,
            source_id=source_id,
            source_url=notif.get("source_url", ""),
            title=full_title,
            description=f"From {repo}" if repo else None,
            confidence_score=confidence_map.get(
                action_type, 0.5
            ),
            priority=priority_map.get(
                action_type, ActionItemPriority.MEDIUM.value
            ),
            status=ActionItemStatus.NEW.value,
            dedup_hash=dedup,
        )
        session.add(action_item)
