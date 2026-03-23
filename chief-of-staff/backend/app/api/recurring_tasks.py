"""Recurring task API endpoints — CRUD + complete/skip + reorder."""

import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.recurring_task import RecurringTask, TaskCompletion
from app.models.user import User
from app.schemas.recurring_task import (
    RecurringTaskCreate,
    RecurringTaskReorderRequest,
    RecurringTaskResponse,
    RecurringTaskUpdate,
    TaskCompletionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=list[RecurringTaskResponse])
def list_recurring_tasks(
    include_archived: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RecurringTaskResponse]:
    """List all recurring tasks, ordered by sort_order."""
    query = db.query(RecurringTask).filter(
        RecurringTask.user_id == current_user.id,
    )
    if not include_archived:
        query = query.filter(RecurringTask.is_archived.is_(False))

    return query.order_by(RecurringTask.sort_order).all()


@router.post(
    "",
    response_model=RecurringTaskResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_recurring_task(
    task_data: RecurringTaskCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecurringTaskResponse:
    """Create a new recurring task."""
    task = RecurringTask(
        user_id=current_user.id,
        title=task_data.title,
        description=task_data.description,
        cadence=task_data.cadence.value,
        cron_expression=task_data.cron_expression,
        start_time=task_data.start_time,
        end_time=task_data.end_time,
        timezone=task_data.timezone,
        missed_behavior=task_data.missed_behavior.value,
        priority=task_data.priority.value,
        sort_order=task_data.sort_order,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.put("/reorder", status_code=status.HTTP_204_NO_CONTENT)
def reorder_tasks(
    reorder: RecurringTaskReorderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Bulk reorder recurring tasks by setting sort_order."""
    tasks = (
        db.query(RecurringTask)
        .filter(
            RecurringTask.user_id == current_user.id,
            RecurringTask.id.in_(reorder.task_ids),
        )
        .all()
    )
    task_map = {t.id: t for t in tasks}
    for idx, task_id in enumerate(reorder.task_ids):
        if task_id in task_map:
            task_map[task_id].sort_order = idx
    db.commit()


@router.put("/{task_id}", response_model=RecurringTaskResponse)
def update_recurring_task(
    task_id: str,
    updates: RecurringTaskUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecurringTaskResponse:
    """Update a recurring task."""
    task = _get_user_task(db, task_id, current_user.id)
    update_data = updates.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None and hasattr(value, "value"):
            value = value.value  # Convert enums to strings
        setattr(task, field, value)
    db.commit()
    db.refresh(task)
    return task


@router.delete(
    "/{task_id}", status_code=status.HTTP_204_NO_CONTENT
)
def archive_recurring_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Archive (soft delete) a recurring task."""
    task = _get_user_task(db, task_id, current_user.id)
    task.is_archived = True
    db.commit()


@router.post(
    "/{task_id}/complete",
    response_model=TaskCompletionResponse,
)
def complete_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskCompletionResponse:
    """Mark a recurring task as complete for today.

    Streak logic:
    - If yesterday was also completed (or first completion),
      increment streak. Otherwise reset to 1.
    """
    task = _get_user_task(db, task_id, current_user.id)
    today = date.today()
    now = datetime.now(tz=timezone.utc)

    # Check if already completed today
    existing = (
        db.query(TaskCompletion)
        .filter(
            TaskCompletion.recurring_task_id == task.id,
            TaskCompletion.date == today,
        )
        .first()
    )
    if existing and existing.completed_at:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Task already completed today",
        )

    if existing:
        existing.completed_at = now
        existing.skipped = False
        completion = existing
    else:
        completion = TaskCompletion(
            recurring_task_id=task.id,
            date=today,
            completed_at=now,
        )
        db.add(completion)

    yesterday = today - timedelta(days=1)
    yesterday_completion = (
        db.query(TaskCompletion)
        .filter(
            TaskCompletion.recurring_task_id == task.id,
            TaskCompletion.date == yesterday,
            TaskCompletion.completed_at.isnot(None),
        )
        .first()
    )

    if yesterday_completion or task.streak_count == 0:
        task.streak_count += 1
    else:
        task.streak_count = 1

    task.last_completed_at = now
    db.commit()
    db.refresh(completion)
    return completion


@router.post(
    "/{task_id}/skip",
    response_model=TaskCompletionResponse,
)
def skip_task(
    task_id: str,
    notes: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskCompletionResponse:
    """Skip a recurring task for today with optional note."""
    task = _get_user_task(db, task_id, current_user.id)
    today = date.today()

    existing = (
        db.query(TaskCompletion)
        .filter(
            TaskCompletion.recurring_task_id == task.id,
            TaskCompletion.date == today,
        )
        .first()
    )
    if existing:
        existing.skipped = True
        existing.notes = notes
        completion = existing
    else:
        completion = TaskCompletion(
            recurring_task_id=task.id,
            date=today,
            skipped=True,
            notes=notes,
        )
        db.add(completion)

    db.commit()
    db.refresh(completion)
    return completion


# --- Helpers ---


def _get_user_task(
    db: Session, task_id: str, user_id: str
) -> RecurringTask:
    """Fetch a recurring task owned by the user, or raise 404."""
    task = (
        db.query(RecurringTask)
        .filter(
            RecurringTask.id == task_id,
            RecurringTask.user_id == user_id,
        )
        .first()
    )
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recurring task not found",
        )
    return task
