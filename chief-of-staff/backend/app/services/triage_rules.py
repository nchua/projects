"""Adaptive triage rules — structured pre/post-filtering.

Research-informed approach: SaneBox, Gmail Priority Inbox, and
SpamAssassin all use structured rules — not LLM prompt injection —
for adaptive filtering. MIT 2026 shows prompt-based personalization
leads to sycophancy.

Key design:
- Code-level pre/post-filtering (deterministic, testable, debuggable)
- Cold start: no adaptive adjustments until 20+ dismissals per source
- Threshold escalation: high-dismissal sources get raised thresholds
"""

import logging
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.action_item import ActionItem
from app.models.contact import Contact
from app.models.enums import ActionItemStatus

logger = logging.getLogger(__name__)

# Cold start: minimum dismissals before adapting
COLD_START_THRESHOLD = 20

# Default confidence threshold for new/low-volume sources
DEFAULT_CONFIDENCE_THRESHOLD = 0.5

# Dismissal rate thresholds for escalation
MEDIUM_DISMISSAL_RATE = 0.50  # >50% → raise to 0.7
HIGH_DISMISSAL_RATE = 0.70    # >70% → raise to 0.85

# Recompute triage_config every N dismissals
RECOMPUTE_INTERVAL = 10


def get_source_threshold(
    user_id: str, source: str, db: Session
) -> float:
    """Return the confidence threshold for a source.

    Higher thresholds mean only high-confidence items are persisted.
    Default: 0.5. High-dismissal sources get raised thresholds.
    """
    from app.models.user import User

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.triage_config:
        return DEFAULT_CONFIDENCE_THRESHOLD

    thresholds = user.triage_config.get("source_thresholds", {})
    return thresholds.get(source, DEFAULT_CONFIDENCE_THRESHOLD)


def compute_triage_config(user_id: str, db: Session) -> dict[str, Any]:
    """Aggregate dismissal stats per source and compute thresholds.

    Returns a triage_config dict with per-source confidence thresholds
    and suppressed senders.
    """
    # Get distinct sources for this user
    sources = (
        db.query(ActionItem.source)
        .filter(ActionItem.user_id == user_id)
        .distinct()
        .all()
    )

    source_thresholds: dict[str, float] = {}
    for (source,) in sources:
        total = (
            db.query(func.count(ActionItem.id))
            .filter(
                ActionItem.user_id == user_id,
                ActionItem.source == source,
            )
            .scalar()
        ) or 0

        dismissed = (
            db.query(func.count(ActionItem.id))
            .filter(
                ActionItem.user_id == user_id,
                ActionItem.source == source,
                ActionItem.status == ActionItemStatus.DISMISSED.value,
            )
            .scalar()
        ) or 0

        if dismissed < COLD_START_THRESHOLD:
            continue

        rate = dismissed / max(total, 1)

        if rate > HIGH_DISMISSAL_RATE:
            source_thresholds[source] = 0.85
        elif rate > MEDIUM_DISMISSAL_RATE:
            source_thresholds[source] = 0.7

    # Compute suppressed senders
    suppressed_senders = _compute_suppressed_senders(user_id, db)

    return {
        "source_thresholds": source_thresholds,
        "suppressed_senders": suppressed_senders,
    }


def should_suppress_sender(
    user_id: str, sender: str, db: Session
) -> bool:
    """Check if this sender's items are dismissed >70% of the time.

    Uses cached triage_config from user when available.
    """
    if not sender:
        return False

    from app.models.user import User

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.triage_config:
        return False

    suppressed = user.triage_config.get("suppressed_senders", [])
    return sender.lower() in [s.lower() for s in suppressed]


def maybe_recompute_triage_config(
    user_id: str, db: Session
) -> None:
    """Recompute triage_config if we've hit a recompute interval.

    Called after each dismissal. Only recomputes every RECOMPUTE_INTERVAL
    dismissals to avoid excessive computation.
    """
    total_dismissed = (
        db.query(func.count(ActionItem.id))
        .filter(
            ActionItem.user_id == user_id,
            ActionItem.status == ActionItemStatus.DISMISSED.value,
        )
        .scalar()
    ) or 0

    if total_dismissed > 0 and total_dismissed % RECOMPUTE_INTERVAL == 0:
        from app.models.user import User

        config = compute_triage_config(user_id, db)
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.triage_config = config
            db.flush()
            logger.info(
                "Recomputed triage_config for user %s: %s",
                user_id,
                config,
            )


def _compute_suppressed_senders(
    user_id: str, db: Session
) -> list[str]:
    """Find senders whose items are dismissed >70% of the time.

    Uses contact dismissal stats. Requires COLD_START_THRESHOLD
    action items from the sender before suppressing.
    """
    contacts = (
        db.query(Contact)
        .filter(
            Contact.user_id == user_id,
            Contact.action_item_count >= COLD_START_THRESHOLD,
        )
        .all()
    )

    suppressed = []
    for contact in contacts:
        if contact.action_item_count == 0:
            continue
        rate = contact.dismissal_count / contact.action_item_count
        if rate > HIGH_DISMISSAL_RATE and contact.email:
            suppressed.append(contact.email)

    return suppressed
