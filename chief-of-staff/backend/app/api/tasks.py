"""Unified tasks endpoint — merged view of tasks, reminders, and action items."""

import logging
from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.action_item import ActionItem
from app.models.one_off_reminder import OneOffReminder
from app.models.recurring_task import RecurringTask, TaskCompletion
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()

# Priority sort order (lower = higher priority)
_PRIORITY_ORDER = {
    "non_negotiable": 0,
    "high": 1,
    "medium": 2,
    "flexible": 3,
    "low": 4,
}


@router.get("/today")
def get_today_tasks(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Combined view of today's tasks.

    Returns recurring tasks (with completion status), pending
    reminders, and open action items — merged and sorted by
    priority.
    """
    today = date.today()

    # Recurring tasks due today
    recurring = _get_recurring_for_today(
        db, current_user.id, today
    )

    # Pending reminders
    reminders = (
        db.query(OneOffReminder)
        .filter(
            OneOffReminder.user_id == current_user.id,
            OneOffReminder.status == "pending",
        )
        .order_by(OneOffReminder.created_at)
        .all()
    )

    # Open action items
    action_items = (
        db.query(ActionItem)
        .filter(
            ActionItem.user_id == current_user.id,
            ActionItem.status.in_(["new", "acknowledged"]),
        )
        .order_by(ActionItem.created_at.desc())
        .limit(20)
        .all()
    )

    return {
        "date": today.isoformat(),
        "recurring_tasks": recurring,
        "reminders": [
            {
                "id": r.id,
                "type": "reminder",
                "title": r.title,
                "description": r.description,
                "trigger_type": r.trigger_type,
                "status": r.status,
                "priority": "medium",
            }
            for r in reminders
        ],
        "action_items": [
            {
                "id": a.id,
                "type": "action_item",
                "title": a.title,
                "source": a.source,
                "priority": a.priority,
                "status": a.status,
                "confidence_score": a.confidence_score,
            }
            for a in action_items
        ],
    }


@router.get("/all")
def get_all_tasks(
    task_type: Optional[str] = Query(
        None,
        description="Filter: recurring, action_item, reminder",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """All tasks, optionally filtered by type."""
    result: dict[str, Any] = {}

    if task_type is None or task_type == "recurring":
        tasks = (
            db.query(RecurringTask)
            .filter(
                RecurringTask.user_id == current_user.id,
                RecurringTask.is_archived.is_(False),
            )
            .order_by(RecurringTask.sort_order)
            .all()
        )
        result["recurring_tasks"] = [
            {
                "id": t.id,
                "type": "recurring",
                "title": t.title,
                "cadence": t.cadence,
                "priority": t.priority,
                "streak_count": t.streak_count,
                "is_archived": t.is_archived,
            }
            for t in tasks
        ]

    if task_type is None or task_type == "action_item":
        items = (
            db.query(ActionItem)
            .filter(
                ActionItem.user_id == current_user.id,
                ActionItem.status.in_(
                    ["new", "acknowledged"]
                ),
            )
            .order_by(ActionItem.created_at.desc())
            .all()
        )
        result["action_items"] = [
            {
                "id": a.id,
                "type": "action_item",
                "title": a.title,
                "source": a.source,
                "priority": a.priority,
                "status": a.status,
            }
            for a in items
        ]

    if task_type is None or task_type == "reminder":
        reminders = (
            db.query(OneOffReminder)
            .filter(
                OneOffReminder.user_id == current_user.id,
                OneOffReminder.status == "pending",
            )
            .order_by(OneOffReminder.created_at)
            .all()
        )
        result["reminders"] = [
            {
                "id": r.id,
                "type": "reminder",
                "title": r.title,
                "trigger_type": r.trigger_type,
                "status": r.status,
            }
            for r in reminders
        ]

    return result


def _get_recurring_for_today(
    db: Session, user_id: str, today: date
) -> list[dict[str, Any]]:
    """Get recurring tasks due today with completion status."""
    tasks = (
        db.query(RecurringTask)
        .filter(
            RecurringTask.user_id == user_id,
            RecurringTask.is_archived.is_(False),
        )
        .order_by(RecurringTask.sort_order)
        .all()
    )

    day_of_week = today.weekday()
    day_of_month = today.day
    result = []

    for task in tasks:
        is_due = False
        if task.cadence == "daily":
            is_due = True
        elif task.cadence == "weekly" and day_of_week == 0:
            is_due = True
        elif task.cadence == "monthly" and day_of_month == 1:
            is_due = True

        if not is_due:
            continue

        # Check completion status
        completion = (
            db.query(TaskCompletion)
            .filter(
                TaskCompletion.recurring_task_id == task.id,
                TaskCompletion.date == today,
            )
            .first()
        )

        result.append({
            "id": task.id,
            "type": "recurring",
            "title": task.title,
            "cadence": task.cadence,
            "priority": task.priority,
            "streak_count": task.streak_count,
            "completed_today": (
                completion is not None
                and completion.completed_at is not None
            ),
            "skipped_today": (
                completion is not None and completion.skipped
            ),
        })

    return result
