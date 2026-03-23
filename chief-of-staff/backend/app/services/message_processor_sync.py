"""Synchronous message processor for manual sync (no Redis/arq needed).

Mirrors the async message_processor.py pipeline but uses a sync
SQLAlchemy Session. AI calls (triage, extract) are awaited directly
since the caller (sync_integration_now) is already async.
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.action_item import ActionItem
from app.models.enums import (
    ActionItemPriority,
    ActionItemSource,
    ActionItemStatus,
    IntegrationProvider,
)
from app.services.email_preprocessor import hash_content, preprocess_body
from app.services.extraction_service import (
    extract_action_items,
    triage_message,
)
from app.services.triage_rules import get_source_threshold, should_suppress_sender

logger = logging.getLogger(__name__)

MIN_BODY_CHARS = 50

# Providers that go through AI extraction
MESSAGE_PROVIDERS = {
    IntegrationProvider.GMAIL.value,
    IntegrationProvider.GITHUB.value,
    IntegrationProvider.SLACK.value,
    IntegrationProvider.GRANOLA.value,
}


async def process_messages_inline(
    db: Session,
    user_id: str,
    provider: str,
    messages: list[dict[str, Any]],
) -> int:
    """Process messages inline during manual sync (no Redis needed).

    Uses sync Session for DB ops but awaits async AI calls.
    Returns count of action items created.
    """
    if not messages:
        return 0

    if provider == IntegrationProvider.GITHUB.value:
        return _process_github_sync(db, user_id, messages)
    elif provider == IntegrationProvider.GMAIL.value:
        return await _process_text_messages_sync(
            db, user_id, messages, "gmail", ActionItemSource.GMAIL.value
        )
    elif provider == IntegrationProvider.SLACK.value:
        return await _process_text_messages_sync(
            db, user_id, messages, "slack", ActionItemSource.SLACK.value
        )
    elif provider == IntegrationProvider.GRANOLA.value:
        return await _process_text_messages_sync(
            db, user_id, messages, "granola", ActionItemSource.GRANOLA.value
        )

    return 0


def _process_github_sync(
    db: Session,
    user_id: str,
    notifications: list[dict[str, Any]],
) -> int:
    """Process GitHub notifications — structured extraction, no AI."""
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

    count = 0
    for notif in notifications:
        action_type = notif.get("action_type", "other")
        if action_type not in actionable_types:
            continue

        source_id = notif.get("source_id", "")
        dedup = hash_content(f"github:{source_id}")

        existing = (
            db.query(ActionItem)
            .filter(
                ActionItem.dedup_hash == dedup,
                ActionItem.user_id == user_id,
            )
            .first()
        )
        if existing:
            continue

        title = notif.get("title", "(No title)")
        prefix = title_prefix_map.get(action_type, "")
        full_title = (f"{prefix}: {title}" if prefix else title)[:200]
        repo = notif.get("repository", "")

        action_item = ActionItem(
            user_id=user_id,
            source=ActionItemSource.GITHUB.value,
            source_id=source_id,
            source_url=notif.get("source_url", ""),
            title=full_title,
            description=f"From {repo}" if repo else None,
            confidence_score=confidence_map.get(action_type, 0.5),
            priority=priority_map.get(action_type, ActionItemPriority.MEDIUM.value),
            status=ActionItemStatus.NEW.value,
            dedup_hash=dedup,
        )
        db.add(action_item)
        count += 1

    return count


async def _process_text_messages_sync(
    db: Session,
    user_id: str,
    messages: list[dict[str, Any]],
    source_label: str,
    source_value: str,
) -> int:
    """Process Gmail/Slack/Granola messages through AI triage + extraction.

    Uses sync Session for DB, awaits async AI calls.
    """
    confidence_threshold = get_source_threshold(user_id, source_label, db)
    count = 0

    for msg in messages:
        body = msg.get("body", "")
        source_id = msg.get("source_id", "")
        sender = msg.get("sender", "")

        # Sender suppression (not applicable for granola)
        if sender and should_suppress_sender(user_id, sender, db):
            continue

        # Preprocess (Gmail needs HTML stripping; Slack/Granola are plain text)
        if source_label == "gmail":
            processed_body = preprocess_body(body)
        else:
            processed_body = body

        if len(processed_body) < MIN_BODY_CHARS:
            continue

        # Dedup check
        content_hash = hash_content(f"{source_id}:{processed_body[:500]}")
        existing = (
            db.query(ActionItem)
            .filter(
                ActionItem.dedup_hash == content_hash,
                ActionItem.user_id == user_id,
            )
            .first()
        )
        if existing:
            continue

        # Build subject for triage
        subject = msg.get("subject", "")
        if source_label == "slack":
            channel = msg.get("channel", "")
            subject = f"Message in #{channel}"
        elif source_label == "granola":
            title = msg.get("title", "")
            subject = f"Meeting: {title}"

        # AI triage (Haiku)
        should_extract = await triage_message(
            processed_body, source_label, subject, sender
        )
        if not should_extract:
            continue

        # AI extraction (Sonnet)
        extracted = await extract_action_items(
            processed_body,
            source=source_label,
            source_id=source_id,
            source_url=msg.get("source_url", ""),
            subject=subject,
            sender=sender,
        )

        # Persist extracted items
        for item_data in extracted:
            confidence = item_data.get("confidence_score") or 0.5
            if confidence < confidence_threshold:
                continue

            dedup = item_data.get("dedup_hash")
            if dedup:
                dup = (
                    db.query(ActionItem)
                    .filter(
                        ActionItem.dedup_hash == dedup,
                        ActionItem.user_id == user_id,
                    )
                    .first()
                )
                if dup:
                    continue

            action_item = ActionItem(
                user_id=user_id,
                source=source_value,
                source_id=item_data.get("source_id"),
                source_url=item_data.get("source_url"),
                title=item_data["title"],
                description=item_data.get("description"),
                confidence_score=confidence,
                priority=item_data.get("priority", ActionItemPriority.MEDIUM.value),
                status=ActionItemStatus.NEW.value,
                dedup_hash=dedup,
            )
            db.add(action_item)
            count += 1

        # Memory extraction (graceful degradation)
        try:
            from app.services.memory_service import (
                extract_memory_facts,
                persist_memory_facts,
            )

            facts = await extract_memory_facts(
                processed_body, source_label, source_id,
                msg.get("source_url", ""),
            )
            if facts:
                persist_memory_facts(facts, user_id, db)
        except Exception as e:
            logger.warning("Memory extraction failed (non-fatal): %s", e)

    return count
