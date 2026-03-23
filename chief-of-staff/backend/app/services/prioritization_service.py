"""Smart prioritization — RFM-based contact scoring + composite action item ranking.

Research-informed approach:
- RFM (Recency-Frequency-Monetary) framework for contact importance
- Exponential decay with 30-day half-life (SaneBox/Gmail pattern)
- Composite scoring for action items at query time (deadline urgency changes hourly)
- Dismissal penalty to down-rank unreliable sources/contacts
"""

import logging
import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.action_item import ActionItem
from app.models.contact import ActionItemContact, Contact
from app.models.enums import ActionItemStatus

logger = logging.getLogger(__name__)

# Scoring weights for composite action item score
WEIGHT_PRIORITY = 0.30
WEIGHT_CONTACT = 0.25
WEIGHT_SOURCE_RELIABILITY = 0.20
WEIGHT_CONFIDENCE = 0.15
WEIGHT_DEADLINE = 0.10

# Contact importance parameters
RECENCY_HALF_LIFE_DAYS = 30
FREQUENCY_CAP = 50  # log-normalized against this value


def compute_contact_importance(
    contact: Contact,
    important_contact_ids: list[str] | None = None,
) -> float:
    """Compute importance score for a contact using RFM model.

    Args:
        contact: The contact to score.
        important_contact_ids: List of contact IDs explicitly marked important.

    Returns:
        Score between 0.0 and 1.0.
    """
    # Base: explicitly important contacts get a boost
    if important_contact_ids and contact.id in important_contact_ids:
        base = 1.0
    else:
        base = 0.5

    # Recency: exponential decay, half-life 30 days
    now = datetime.now(tz=timezone.utc)
    if contact.last_interaction_at:
        last = contact.last_interaction_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        days_since = max((now - last).days, 0)
    else:
        days_since = 90  # Default for no interactions

    recency = 0.5 ** (days_since / RECENCY_HALF_LIFE_DAYS)

    # Frequency: log-normalized interaction count
    count = contact.interaction_count or 0
    frequency = min(
        math.log(count + 1) / math.log(FREQUENCY_CAP), 1.0
    )

    # Dismissal penalty
    action_items = contact.action_item_count or 0
    dismissals = contact.dismissal_count or 0
    dismissal_rate = dismissals / max(action_items, 1)
    penalty = 1.0 - (dismissal_rate * 0.5)

    score = base * recency * frequency * penalty
    return _clamp(score, 0.0, 1.0)


def score_action_item(
    item: ActionItem,
    contact_score: float,
    source_dismissal_rate: float,
) -> float:
    """Compute composite score for an action item.

    This is computed at query time because deadline urgency changes.

    Args:
        item: The action item to score.
        contact_score: Pre-computed importance of associated contact.
        source_dismissal_rate: Dismissal rate for this item's source.

    Returns:
        Score between 0.0 and 1.0.
    """
    priority_scores = {"high": 1.0, "medium": 0.6, "low": 0.3}
    priority_score = priority_scores.get(item.priority, 0.5)

    source_reliability = 1.0 - source_dismissal_rate
    confidence = item.confidence_score or 0.5
    deadline_urgency = _compute_deadline_urgency(
        item.extracted_deadline
    )

    return (
        WEIGHT_PRIORITY * priority_score
        + WEIGHT_CONTACT * contact_score
        + WEIGHT_SOURCE_RELIABILITY * source_reliability
        + WEIGHT_CONFIDENCE * confidence
        + WEIGHT_DEADLINE * deadline_urgency
    )


def rerank_action_items(
    items: list[ActionItem],
    user_id: str,
    db: Session,
) -> list[ActionItem]:
    """Rerank action items by composite score.

    Looks up contact scores and source dismissal rates, then
    sorts items by composite score descending.
    """
    if not items:
        return items

    # Pre-compute source dismissal rates
    source_rates = _get_source_dismissal_rates(user_id, db)

    # Pre-compute contact scores (batch lookup)
    contact_scores = _get_contact_scores_for_items(items, db)

    # Score and sort
    scored = []
    for item in items:
        contact_score = contact_scores.get(item.id, 0.5)
        source_rate = source_rates.get(item.source, 0.0)
        score = score_action_item(item, contact_score, source_rate)
        scored.append((item, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [item for item, _ in scored]


def update_contact_on_extract(
    sender_info: dict[str, str | None],
    user_id: str,
    db: Session,
) -> Contact | None:
    """Find-or-create contact, increment counts, recompute score.

    Args:
        sender_info: Dict with 'email', 'name' keys.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The updated or created Contact, or None if no identifier.
    """
    email = sender_info.get("email")
    name = sender_info.get("name", "")

    if not email and not name:
        return None

    # Try to find existing contact
    contact = None
    if email:
        contact = (
            db.query(Contact)
            .filter(
                Contact.user_id == user_id,
                Contact.email == email,
            )
            .first()
        )

    if not contact and name:
        contact = (
            db.query(Contact)
            .filter(
                Contact.user_id == user_id,
                Contact.display_name == name,
            )
            .first()
        )

    now = datetime.now(tz=timezone.utc)

    if contact:
        contact.interaction_count = (contact.interaction_count or 0) + 1
        contact.action_item_count = (contact.action_item_count or 0) + 1
        contact.last_interaction_at = now
    else:
        contact = Contact(
            user_id=user_id,
            display_name=name or (email or "Unknown"),
            email=email,
            last_interaction_at=now,
            interaction_count=1,
            action_item_count=1,
            dismissal_count=0,
            importance_score=0.5,
        )
        db.add(contact)

    # Recompute importance
    contact.importance_score = compute_contact_importance(contact)
    db.flush()
    return contact


def refresh_all_contact_scores(
    user_id: str, db: Session
) -> int:
    """Daily cron: refresh all contact importance scores.

    Applies recency decay to all contacts for a user.

    Returns:
        Number of contacts updated.
    """
    contacts = (
        db.query(Contact)
        .filter(Contact.user_id == user_id)
        .all()
    )

    for contact in contacts:
        contact.importance_score = compute_contact_importance(contact)

    db.flush()
    return len(contacts)


# =============================================================================
# HELPERS
# =============================================================================


def _compute_deadline_urgency(
    deadline: datetime | None,
) -> float:
    """Compute urgency score based on deadline proximity.

    Returns 1.0 for deadlines within 24 hours, declining to 0.0 for
    deadlines more than 7 days away. 0.0 if no deadline.
    """
    if not deadline:
        return 0.0

    now = datetime.now(tz=timezone.utc)
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)

    hours_until = (deadline - now).total_seconds() / 3600

    if hours_until <= 0:
        return 1.0  # Past due
    elif hours_until <= 24:
        return 1.0
    elif hours_until <= 48:
        return 0.8
    elif hours_until <= 168:  # 7 days
        return 0.4
    else:
        return 0.1


def _get_source_dismissal_rates(
    user_id: str, db: Session
) -> dict[str, float]:
    """Get dismissal rates per source for a user."""
    source_stats = (
        db.query(ActionItem.source)
        .filter(ActionItem.user_id == user_id)
        .group_by(ActionItem.source)
        .all()
    )

    rates = {}
    for (source,) in source_stats:
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

        rates[source] = dismissed / max(total, 1)

    return rates


def _get_contact_scores_for_items(
    items: list[ActionItem], db: Session
) -> dict[str, float]:
    """Get contact importance scores for a batch of action items.

    Returns a dict mapping action_item_id → best contact score.
    """
    item_ids = [item.id for item in items]
    if not item_ids:
        return {}

    links = (
        db.query(ActionItemContact)
        .filter(ActionItemContact.action_item_id.in_(item_ids))
        .all()
    )

    contact_ids = list({link.contact_id for link in links})
    if not contact_ids:
        return {}

    contacts = (
        db.query(Contact)
        .filter(Contact.id.in_(contact_ids))
        .all()
    )
    contact_map = {c.id: c.importance_score or 0.5 for c in contacts}

    # Map item_id → best contact score
    result: dict[str, float] = {}
    for link in links:
        score = contact_map.get(link.contact_id, 0.5)
        if link.action_item_id not in result:
            result[link.action_item_id] = score
        else:
            result[link.action_item_id] = max(
                result[link.action_item_id], score
            )

    return result


def _clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp a value between min and max."""
    return max(min_val, min(max_val, value))
