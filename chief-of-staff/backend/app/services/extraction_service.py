"""AI extraction service — two-tier triage + extraction pipeline.

Tier 1 (Haiku): Quick yes/no — does this message contain action items?
Tier 2 (Sonnet): Full structured extraction of action items.

Per spec: Data minimization first, Haiku for triage, Sonnet only
for messages that pass triage. Audit log every AI call (without content).
"""

import json
import logging
from typing import Any

import anthropic
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.action_item import ActionItem
from app.models.enums import (
    ActionItemPriority,
    ActionItemSource,
    ActionItemStatus,
)
from app.services.audit_log import log_audit
from app.services.email_preprocessor import (
    hash_content,
    preprocess_body,
)

logger = logging.getLogger(__name__)

# Model configuration
TRIAGE_MODEL = "claude-haiku-4-5-20251001"
EXTRACTION_MODEL = "claude-sonnet-4-5-20250514"

# Per-message cost estimates (for logging/auditing)
# Haiku: ~$0.80/$4.00 per 1M tokens
# Sonnet: ~$3.00/$15.00 per 1M tokens

DEFAULT_USER_NAME = "Nick"


# =============================================================================
# PROMPT TEMPLATES (ported from prompt-harness/prompts.py)
# =============================================================================

_TRIAGE_SYSTEM = """\
You are an email/message triage assistant. Your ONLY job is to \
determine whether a message contains actionable items that the \
recipient ({user_name}) needs to act on.

Answer with a JSON object: \
{{"has_action_items": true/false, "reasoning": "one sentence"}}

Action items include:
- Direct requests to {user_name}
- Commitments {user_name} made that someone is referencing
- Assignments (PR reviews, issues, tasks assigned to {user_name})
- Questions that need a response from {user_name}
- Deadlines directed at {user_name}

NOT action items:
- Newsletters, digests, marketing emails
- Receipts, shipping confirmations, order updates
- Automated notifications that are purely informational
- FYI messages where the sender explicitly says "no action needed"
- General announcements"""

_EXTRACTION_SYSTEM = """\
You are an action item extraction assistant. Given an email or \
message, extract all actionable items that the recipient \
({user_name}) needs to act on.

For each action item, return:
- title: Short imperative phrase (max 80 chars)
- description: Brief context (1-2 sentences)
- people: Names of people involved
- deadline: Exact phrasing from message, or null
- confidence: 0.0 to 1.0
- priority: "high" | "medium" | "low"
- commitment_type: "you_committed" | "they_requested" | \
"mutual" | "fyi"

Rules:
1. Only extract items {user_name} personally needs to act on.
2. Merge closely related sub-tasks into a single action item.
3. Focus on the most recent message in threads.
4. If "no action needed" or "FYI only", return empty list.

Respond with JSON only:
{{"action_items": [{{...}}]}}"""

_USER_TEMPLATE = """\
Source: {source}
Subject: {subject}
From: {sender}

---
{body}
---

{instruction}"""


# =============================================================================
# TRIAGE (Haiku)
# =============================================================================


async def triage_message(
    text: str,
    source: str,
    subject: str = "",
    sender: str = "",
    user_name: str = DEFAULT_USER_NAME,
) -> bool:
    """Quick triage: does this message contain action items?

    Uses Haiku for speed and cost. Returns True if the message
    is worth sending to the full extraction pipeline.
    """
    settings = get_settings()
    if not settings.anthropic_api_key:
        logger.warning("No Anthropic API key — skipping triage")
        return True  # Fail open: if no key, assume worth extracting

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    user_prompt = _USER_TEMPLATE.format(
        source=source,
        subject=subject,
        sender=sender,
        body=text,
        instruction=(
            f"Does this message contain action items for "
            f"{user_name}? Respond with JSON only."
        ),
    )

    try:
        response = client.messages.create(
            model=TRIAGE_MODEL,
            max_tokens=256,
            system=_TRIAGE_SYSTEM.format(user_name=user_name),
            messages=[{"role": "user", "content": user_prompt}],
        )

        content = response.content[0].text
        result = json.loads(content)
        return bool(result.get("has_action_items", False))

    except (json.JSONDecodeError, IndexError, KeyError) as e:
        logger.warning("Triage parse error: %s", e)
        return True  # Fail open on parse error
    except Exception as e:
        logger.error("Triage API call failed: %s", e)
        return True  # Fail open on API error


# =============================================================================
# EXTRACTION (Sonnet)
# =============================================================================


async def extract_action_items(
    text: str,
    source: str,
    source_id: str,
    source_url: str,
    subject: str = "",
    sender: str = "",
    user_name: str = DEFAULT_USER_NAME,
) -> list[dict[str, Any]]:
    """Extract structured action items from a message.

    Uses Sonnet for quality. Returns a list of dicts matching
    the ActionItemCreate schema fields.
    """
    settings = get_settings()
    if not settings.anthropic_api_key:
        logger.warning("No Anthropic API key — skipping extraction")
        return []

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    user_prompt = _USER_TEMPLATE.format(
        source=source,
        subject=subject,
        sender=sender,
        body=text,
        instruction=(
            f"Extract all action items for {user_name} "
            f"from this message. Respond with JSON only."
        ),
    )

    try:
        response = client.messages.create(
            model=EXTRACTION_MODEL,
            max_tokens=2048,
            system=_EXTRACTION_SYSTEM.format(user_name=user_name),
            messages=[{"role": "user", "content": user_prompt}],
        )

        content = response.content[0].text
        result = json.loads(content)
        items = result.get("action_items", [])

        # Normalize and enrich each item
        normalized = []
        for item in items:
            normalized.append({
                "source": source,
                "source_id": source_id,
                "source_url": source_url,
                "title": item.get("title", "")[:200],
                "description": item.get("description"),
                "people": item.get("people", []),
                "deadline_raw": item.get("deadline"),
                "confidence_score": _clamp(
                    item.get("confidence", 0.5), 0.0, 1.0
                ),
                "priority": _normalize_priority(
                    item.get("priority", "medium")
                ),
                "commitment_type": item.get(
                    "commitment_type", "they_requested"
                ),
                "dedup_hash": hash_content(
                    f"{source_id}:{item.get('title', '')}"
                ),
            })

        return normalized

    except (json.JSONDecodeError, IndexError, KeyError) as e:
        logger.warning("Extraction parse error: %s", e)
        return []
    except Exception as e:
        logger.error("Extraction API call failed: %s", e)
        return []


# =============================================================================
# FULL PIPELINES
# =============================================================================


async def process_gmail_messages(
    messages: list[dict[str, Any]],
    user_id: str,
    db: Session,
) -> list[ActionItem]:
    """Full Gmail pipeline: preprocess, dedup, triage, extract, persist.

    Args:
        messages: Raw message dicts from GmailConnector.sync().
        user_id: The user who owns these messages.
        db: Database session.

    Returns:
        List of newly created ActionItem records.
    """
    created_items: list[ActionItem] = []

    for msg in messages:
        body = msg.get("body", "")
        source_id = msg.get("source_id", "")
        source_url = msg.get("source_url", "")
        subject = msg.get("subject", "")
        sender = msg.get("sender", "")

        # Preprocess (data minimization)
        processed_body = preprocess_body(body)
        if len(processed_body) < 50:
            continue

        # Dedup check
        content_hash = hash_content(
            f"{source_id}:{processed_body[:500]}"
        )
        existing = (
            db.query(ActionItem)
            .filter(ActionItem.dedup_hash == content_hash)
            .first()
        )
        if existing:
            continue

        # Triage (Haiku)
        should_extract = await triage_message(
            processed_body, "gmail", subject, sender
        )

        log_audit(
            db,
            "ai_triage",
            user_id=user_id,
            metadata={
                "source": "gmail",
                "source_id": source_id,
                "result": should_extract,
            },
        )

        if not should_extract:
            continue

        # Extract (Sonnet)
        extracted = await extract_action_items(
            processed_body,
            source="gmail",
            source_id=source_id,
            source_url=source_url,
            subject=subject,
            sender=sender,
        )

        log_audit(
            db,
            "ai_extraction",
            user_id=user_id,
            metadata={
                "source": "gmail",
                "source_id": source_id,
                "items_extracted": len(extracted),
            },
        )

        # Persist
        for item_data in extracted:
            # Check dedup for each extracted item
            if item_data.get("dedup_hash"):
                dup = (
                    db.query(ActionItem)
                    .filter(
                        ActionItem.dedup_hash
                        == item_data["dedup_hash"]
                    )
                    .first()
                )
                if dup:
                    continue

            action_item = ActionItem(
                user_id=user_id,
                source=ActionItemSource.GMAIL.value,
                source_id=item_data.get("source_id"),
                source_url=item_data.get("source_url"),
                title=item_data["title"],
                description=item_data.get("description"),
                confidence_score=item_data.get("confidence_score"),
                priority=item_data.get(
                    "priority", ActionItemPriority.MEDIUM.value
                ),
                status=ActionItemStatus.NEW.value,
                dedup_hash=item_data.get("dedup_hash"),
            )
            db.add(action_item)
            created_items.append(action_item)

    db.flush()
    return created_items


async def process_github_notifications(
    notifications: list[dict[str, Any]],
    user_id: str,
    db: Session,
) -> list[ActionItem]:
    """Process GitHub notifications into action items.

    GitHub notifications have structured data, so we can extract
    action items directly without AI in most cases.
    PR review requests and issue assignments are clear action items.
    """
    created_items: list[ActionItem] = []

    # Action types that are clearly actionable
    actionable_types = {
        "pr_review_requested",
        "issue_assigned",
        "ci_failure",
        "mentioned",
    }

    for notif in notifications:
        action_type = notif.get("action_type", "other")
        if action_type not in actionable_types:
            continue

        source_id = notif.get("source_id", "")
        dedup = hash_content(f"github:{source_id}")

        # Dedup check
        existing = (
            db.query(ActionItem)
            .filter(ActionItem.dedup_hash == dedup)
            .first()
        )
        if existing:
            continue

        # Map action type to priority
        priority_map = {
            "pr_review_requested": ActionItemPriority.MEDIUM.value,
            "issue_assigned": ActionItemPriority.MEDIUM.value,
            "ci_failure": ActionItemPriority.HIGH.value,
            "mentioned": ActionItemPriority.LOW.value,
        }

        # Map action type to confidence
        confidence_map = {
            "pr_review_requested": 0.95,
            "issue_assigned": 0.95,
            "ci_failure": 0.90,
            "mentioned": 0.70,
        }

        # Build title based on type
        title = notif.get("title", "(No title)")
        repo = notif.get("repository", "")
        title_prefix = {
            "pr_review_requested": "Review PR",
            "issue_assigned": "Resolve issue",
            "ci_failure": "Fix CI failure",
            "mentioned": "Respond to mention",
        }
        prefix = title_prefix.get(action_type, "")
        full_title = (
            f"{prefix}: {title}" if prefix else title
        )[:200]

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
        db.add(action_item)
        created_items.append(action_item)

    db.flush()

    if created_items:
        log_audit(
            db,
            "github_extraction",
            user_id=user_id,
            metadata={
                "notifications_processed": len(notifications),
                "items_created": len(created_items),
            },
        )

    return created_items


# =============================================================================
# HELPERS
# =============================================================================


def _clamp(value: float, low: float, high: float) -> float:
    """Clamp a value between low and high."""
    return max(low, min(high, value))


def _normalize_priority(raw: str) -> str:
    """Normalize priority string to a valid enum value."""
    raw_lower = raw.lower().strip()
    if raw_lower in ("high", "medium", "low"):
        return raw_lower
    return "medium"
