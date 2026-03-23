"""One-off reminder API endpoints."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.enums import ReminderStatus
from app.models.one_off_reminder import OneOffReminder
from app.models.user import User
from app.schemas.one_off_reminder import (
    ReminderCreate,
    ReminderResponse,
    ReminderUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=list[ReminderResponse])
def list_reminders(
    include_completed: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ReminderResponse]:
    """List reminders. By default shows only pending."""
    query = db.query(OneOffReminder).filter(
        OneOffReminder.user_id == current_user.id,
    )
    if not include_completed:
        query = query.filter(
            OneOffReminder.status == ReminderStatus.PENDING.value
        )
    return (
        query.order_by(OneOffReminder.created_at.desc()).all()
    )


@router.post(
    "",
    response_model=ReminderResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_reminder(
    data: ReminderCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReminderResponse:
    """Create a one-off reminder."""
    reminder = OneOffReminder(
        user_id=current_user.id,
        title=data.title,
        description=data.description,
        trigger_type=data.trigger_type.value,
        trigger_config=data.trigger_config,
        source_action_item_id=data.source_action_item_id,
        status=ReminderStatus.PENDING.value,
    )
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return reminder


@router.put("/{reminder_id}", response_model=ReminderResponse)
def update_reminder(
    reminder_id: str,
    updates: ReminderUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReminderResponse:
    """Update a reminder."""
    reminder = _get_user_reminder(
        db, reminder_id, current_user.id
    )
    update_data = updates.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None and hasattr(value, "value"):
            value = value.value
        setattr(reminder, field, value)
    db.commit()
    db.refresh(reminder)
    return reminder


@router.post(
    "/{reminder_id}/complete",
    response_model=ReminderResponse,
)
def complete_reminder(
    reminder_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReminderResponse:
    """Mark a reminder as completed."""
    reminder = _get_user_reminder(
        db, reminder_id, current_user.id
    )
    reminder.status = ReminderStatus.COMPLETED.value
    reminder.completed_at = datetime.now(tz=timezone.utc)
    db.commit()
    db.refresh(reminder)
    return reminder


@router.post(
    "/{reminder_id}/dismiss",
    response_model=ReminderResponse,
)
def dismiss_reminder(
    reminder_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReminderResponse:
    """Dismiss a reminder."""
    reminder = _get_user_reminder(
        db, reminder_id, current_user.id
    )
    reminder.status = ReminderStatus.DISMISSED.value
    db.commit()
    db.refresh(reminder)
    return reminder


@router.delete(
    "/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_reminder(
    reminder_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Delete a reminder."""
    reminder = _get_user_reminder(
        db, reminder_id, current_user.id
    )
    db.delete(reminder)
    db.commit()


# --- Helpers ---


def _get_user_reminder(
    db: Session, reminder_id: str, user_id: str
) -> OneOffReminder:
    """Fetch a reminder owned by the user, or raise 404."""
    reminder = (
        db.query(OneOffReminder)
        .filter(
            OneOffReminder.id == reminder_id,
            OneOffReminder.user_id == user_id,
        )
        .first()
    )
    if not reminder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reminder not found",
        )
    return reminder
