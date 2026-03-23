"""Unified tasks endpoint — merged view of tasks, reminders, action items."""

import logging
from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.action_item import ActionItem
from app.models.enums import ActionItemStatus, ReminderStatus
from app.models.one_off_reminder import OneOffReminder
from app.models.recurring_task import RecurringTask, TaskCompletion
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/today")
def get_today_tasks(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Combined view of today's tasks, reminders, and action items."""
    today = date.today()

    recurring = _get_recurring_for_today(
        db, current_user.id, today
    )

    reminders = (
        db.query(OneOffReminder)
        .filter(
            OneOffReminder.user_id == current_user.id,
            OneOffReminder.status
            == ReminderStatus.PENDING.value,
        )
        .order_by(OneOffReminder.created_at)
        .all()
    )

    action_items = (
        db.query(ActionItem)
        .filter(
            ActionItem.user_id == current_user.id,
            ActionItem.status.in_([
                ActionItemStatus.NEW.value,
                ActionItemStatus.ACKNOWLEDGED.value,
            ]),
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
            .limit(200)
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
                ActionItem.status.in_([
                    ActionItemStatus.NEW.value,
                    ActionItemStatus.ACKNOWLEDGED.value,
                ]),
            )
            .order_by(ActionItem.created_at.desc())
            .limit(100)
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
                OneOffReminder.status
                == ReminderStatus.PENDING.value,
            )
            .order_by(OneOffReminder.created_at)
            .limit(100)
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
    # Determine which cadences are due today
    due_cadences = ["daily"]
    if today.weekday() == 0:
        due_cadences.append("weekly")
    if today.day == 1:
        due_cadences.append("monthly")

    tasks = (
        db.query(RecurringTask)
        .filter(
            RecurringTask.user_id == user_id,
            RecurringTask.is_archived.is_(False),
            RecurringTask.cadence.in_(due_cadences),
        )
        .order_by(RecurringTask.sort_order)
        .all()
    )

    if not tasks:
        return []

    # Batch-fetch completions for today (avoids N+1)
    task_ids = [t.id for t in tasks]
    completions = (
        db.query(TaskCompletion)
        .filter(
            TaskCompletion.recurring_task_id.in_(task_ids),
            TaskCompletion.date == today,
        )
        .all()
    )
    completion_map = {
        c.recurring_task_id: c for c in completions
    }

    return [
        {
            "id": task.id,
            "type": "recurring",
            "title": task.title,
            "cadence": task.cadence,
            "priority": task.priority,
            "streak_count": task.streak_count,
            "completed_today": (
                (c := completion_map.get(task.id)) is not None
                and c.completed_at is not None
            ),
            "skipped_today": (
                (c := completion_map.get(task.id)) is not None
                and c.skipped
            ),
        }
        for task in tasks
    ]
