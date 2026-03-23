"""Feedback loop service for action item dismissals.

Per spec: When the AI extracts a wrong action item, users can
dismiss with a reason. Dismissal patterns are tracked and used
to refine extraction prompts over time.
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.action_item import ActionItem
from app.models.contact import ActionItemContact, Contact
from app.models.enums import ActionItemStatus, DismissReason


def dismiss_action_item(
    db: Session,
    item_id: str,
    user_id: str,
    reason: DismissReason,
) -> ActionItem:
    """Mark an action item as dismissed with a reason.

    Also updates contact dismissal stats and recomputes triage
    config at regular intervals.

    Args:
        db: Database session.
        item_id: The action item to dismiss.
        user_id: Owner of the action item.
        reason: Why it was dismissed.

    Returns:
        The updated ActionItem.

    Raises:
        ValueError: If the action item doesn't exist or
            doesn't belong to the user.
    """
    item = (
        db.query(ActionItem)
        .filter(
            ActionItem.id == item_id,
            ActionItem.user_id == user_id,
        )
        .first()
    )
    if not item:
        raise ValueError("Action item not found")

    item.status = ActionItemStatus.DISMISSED.value
    item.dismiss_reason = reason.value
    item.actioned_at = datetime.now(tz=timezone.utc)

    # Compute time_to_action if not already set
    if item.created_at and not item.time_to_action_secs:
        delta = datetime.now(tz=timezone.utc) - item.created_at.replace(
            tzinfo=timezone.utc
        ) if item.created_at.tzinfo is None else (
            datetime.now(tz=timezone.utc) - item.created_at
        )
        item.time_to_action_secs = int(delta.total_seconds())

    db.flush()

    # Update contact dismissal stats
    _update_contact_stats_on_dismiss(db, item)

    # Recompute triage config at regular intervals
    from app.services.triage_rules import maybe_recompute_triage_config
    maybe_recompute_triage_config(user_id, db)

    return item


def _update_contact_stats_on_dismiss(
    db: Session, item: ActionItem
) -> None:
    """Increment dismissal_count on linked contacts."""
    links = (
        db.query(ActionItemContact)
        .filter(ActionItemContact.action_item_id == item.id)
        .all()
    )
    for link in links:
        contact = db.query(Contact).filter(
            Contact.id == link.contact_id
        ).first()
        if contact:
            contact.dismissal_count = (contact.dismissal_count or 0) + 1
            db.flush()


def get_dismissal_stats(
    db: Session, user_id: str
) -> dict[str, Any]:
    """Aggregate dismissal patterns for prompt refinement.

    Returns counts by reason and source, useful for identifying
    which sources produce the most false positives.
    """
    # Count by reason
    reason_counts = (
        db.query(
            ActionItem.dismiss_reason,
            func.count(ActionItem.id),
        )
        .filter(
            ActionItem.user_id == user_id,
            ActionItem.status == ActionItemStatus.DISMISSED.value,
            ActionItem.dismiss_reason.isnot(None),
        )
        .group_by(ActionItem.dismiss_reason)
        .all()
    )

    # Count by source
    source_counts = (
        db.query(
            ActionItem.source,
            func.count(ActionItem.id),
        )
        .filter(
            ActionItem.user_id == user_id,
            ActionItem.status == ActionItemStatus.DISMISSED.value,
        )
        .group_by(ActionItem.source)
        .all()
    )

    # Total items vs. dismissed
    total = (
        db.query(func.count(ActionItem.id))
        .filter(ActionItem.user_id == user_id)
        .scalar()
    )
    dismissed = (
        db.query(func.count(ActionItem.id))
        .filter(
            ActionItem.user_id == user_id,
            ActionItem.status == ActionItemStatus.DISMISSED.value,
        )
        .scalar()
    )

    return {
        "total_items": total or 0,
        "total_dismissed": dismissed or 0,
        "dismissal_rate": (
            round(dismissed / total, 3) if total else 0.0
        ),
        "by_reason": {
            reason: count for reason, count in reason_counts
        },
        "by_source": {
            source: count for source, count in source_counts
        },
    }
