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
from app.services.triage_rules import (
    get_source_threshold,
    should_suppress_sender,
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
    is_slack = first.get("source_id", "").startswith("slack:")
    is_granola = first.get("source_id", "").startswith("granola:")

    async with session_factory() as session:
        if is_github:
            await _process_github(
                session, user_id, messages
            )
        elif is_slack:
            await _process_slack(
                session, user_id, messages
            )
        elif is_granola:
            await _process_granola(
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

    # Get adaptive confidence threshold for Gmail
    confidence_threshold = await _get_threshold_async(
        session, user_id, "gmail"
    )

    for msg in messages:
        body = msg.get("body", "")
        source_id = msg.get("source_id", "")
        sender = msg.get("sender", "")

        # Adaptive: suppress senders with high dismissal rates
        if await _is_sender_suppressed(session, user_id, sender):
            logger.debug("Suppressed sender %s for user %s", sender, user_id)
            continue

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
            sender,
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
            sender=sender,
        )

        # Persist (apply adaptive confidence threshold)
        await _persist_extracted_items(
            session, user_id, extracted,
            ActionItemSource.GMAIL.value, confidence_threshold,
        )

        # Extract memory facts in parallel
        await _extract_memory_facts(
            session, user_id, processed_body,
            "gmail", source_id, msg.get("source_url", ""),
        )


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


async def _process_slack(
    session: AsyncSession,
    user_id: str,
    messages: list[dict[str, Any]],
) -> None:
    """Process Slack messages through AI extraction.

    Slack messages are already plain text — no HTML stripping needed.
    Uses the same triage -> extract pipeline as Gmail.
    """
    from sqlalchemy import select

    confidence_threshold = await _get_threshold_async(
        session, user_id, "slack"
    )

    for msg in messages:
        body = msg.get("body", "")
        source_id = msg.get("source_id", "")
        sender = msg.get("sender", "")

        if await _is_sender_suppressed(session, user_id, sender):
            continue

        if len(body) < MIN_BODY_CHARS:
            continue

        # Dedup check
        content_hash = hash_content(
            f"{source_id}:{body[:500]}"
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
        channel = msg.get("channel", "")
        should_extract = await triage_message(
            body,
            "slack",
            f"Message in #{channel}",
            sender,
        )
        if not should_extract:
            continue

        # Extract
        extracted = await extract_action_items(
            body,
            source="slack",
            source_id=source_id,
            source_url=msg.get("source_url", ""),
            subject=f"Slack message in #{channel}",
            sender=sender,
        )

        # Persist with confidence threshold
        await _persist_extracted_items(
            session, user_id, extracted,
            ActionItemSource.SLACK.value, confidence_threshold,
        )

        # Memory extraction
        await _extract_memory_facts(
            session, user_id, body,
            "slack", source_id, msg.get("source_url", ""),
        )


async def _process_granola(
    session: AsyncSession,
    user_id: str,
    meetings: list[dict[str, Any]],
) -> None:
    """Process Granola meeting notes through AI extraction.

    Meeting notes contain free-text content that may have action items.
    Uses the same triage -> extract pipeline.
    """
    from sqlalchemy import select

    confidence_threshold = await _get_threshold_async(
        session, user_id, "granola"
    )

    for meeting in meetings:
        body = meeting.get("body", "")
        source_id = meeting.get("source_id", "")
        title = meeting.get("title", "")

        if len(body) < MIN_BODY_CHARS:
            continue

        # Dedup check
        content_hash = hash_content(
            f"{source_id}:{body[:500]}"
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
            body,
            "granola",
            f"Meeting: {title}",
            "",
        )
        if not should_extract:
            continue

        # Extract
        extracted = await extract_action_items(
            body,
            source="granola",
            source_id=source_id,
            source_url=meeting.get("source_url", ""),
            subject=f"Meeting notes: {title}",
            sender="",
        )

        # Persist with confidence threshold
        await _persist_extracted_items(
            session, user_id, extracted,
            ActionItemSource.GRANOLA.value, confidence_threshold,
        )

        # Memory extraction (meeting notes are rich sources)
        await _extract_memory_facts(
            session, user_id, body,
            "granola", source_id, meeting.get("source_url", ""),
        )


# =============================================================================
# SHARED HELPERS
# =============================================================================


async def _persist_extracted_items(
    session: AsyncSession,
    user_id: str,
    extracted: list[dict[str, Any]],
    source_value: str,
    confidence_threshold: float,
) -> None:
    """Persist extracted action items, applying adaptive confidence filter."""
    from sqlalchemy import select

    for item_data in extracted:
        # Adaptive: skip items below confidence threshold
        confidence = item_data.get("confidence_score") or 0.5
        if confidence < confidence_threshold:
            logger.debug(
                "Filtered item below threshold (%.2f < %.2f): %s",
                confidence,
                confidence_threshold,
                item_data.get("title", ""),
            )
            continue

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
            source=source_value,
            source_id=item_data.get("source_id"),
            source_url=item_data.get("source_url"),
            title=item_data["title"],
            description=item_data.get("description"),
            confidence_score=confidence,
            priority=item_data.get(
                "priority",
                ActionItemPriority.MEDIUM.value,
            ),
            status=ActionItemStatus.NEW.value,
            dedup_hash=dedup,
        )
        session.add(action_item)


async def _get_threshold_async(
    session: AsyncSession, user_id: str, source: str
) -> float:
    """Get adaptive confidence threshold (async wrapper)."""
    from sqlalchemy import select as sa_select
    from app.models.user import User

    result = await session.execute(
        sa_select(User.triage_config).where(User.id == user_id)
    )
    row = result.first()
    if not row or not row[0]:
        return 0.5

    thresholds = row[0].get("source_thresholds", {})
    return thresholds.get(source, 0.5)


async def _is_sender_suppressed(
    session: AsyncSession, user_id: str, sender: str
) -> bool:
    """Check if sender should be suppressed (async wrapper)."""
    if not sender:
        return False

    from sqlalchemy import select as sa_select
    from app.models.user import User

    result = await session.execute(
        sa_select(User.triage_config).where(User.id == user_id)
    )
    row = result.first()
    if not row or not row[0]:
        return False

    suppressed = row[0].get("suppressed_senders", [])
    return sender.lower() in [s.lower() for s in suppressed]


async def _extract_memory_facts(
    session: AsyncSession,
    user_id: str,
    text: str,
    source: str,
    source_id: str,
    source_url: str,
) -> None:
    """Extract and persist memory facts from message text.

    Runs Haiku memory extraction in parallel with action extraction.
    Gracefully degrades if memory extraction fails.
    """
    try:
        from app.services.memory_service import (
            extract_memory_facts,
            persist_memory_facts_async,
        )

        facts = await extract_memory_facts(
            text, source, source_id, source_url
        )
        if facts:
            await persist_memory_facts_async(
                facts, user_id, session
            )
    except Exception as e:
        logger.warning(
            "Memory extraction failed (non-fatal): %s", e
        )
