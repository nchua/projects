"""Recurring task schemas."""

from datetime import date, datetime
from typing import Optional, List

from pydantic import BaseModel

from app.models.enums import Cadence, MissedBehavior, TaskPriority


class RecurringTaskCreate(BaseModel):
    """Schema for creating a recurring task."""

    title: str
    description: Optional[str] = None
    cadence: Cadence
    cron_expression: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    timezone: Optional[str] = None
    missed_behavior: MissedBehavior = MissedBehavior.ROLL_FORWARD
    priority: TaskPriority = TaskPriority.NON_NEGOTIABLE
    sort_order: int = 0


class RecurringTaskUpdate(BaseModel):
    """Schema for updating a recurring task."""

    title: Optional[str] = None
    description: Optional[str] = None
    cadence: Optional[Cadence] = None
    cron_expression: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    timezone: Optional[str] = None
    missed_behavior: Optional[MissedBehavior] = None
    priority: Optional[TaskPriority] = None
    sort_order: Optional[int] = None
    is_archived: Optional[bool] = None


class RecurringTaskResponse(BaseModel):
    """Schema for recurring task in responses."""

    id: str
    title: str
    description: Optional[str] = None
    cadence: str
    cron_expression: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    timezone: Optional[str] = None
    missed_behavior: str
    priority: str
    streak_count: int
    last_completed_at: Optional[datetime] = None
    sort_order: int
    is_archived: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskCompletionCreate(BaseModel):
    """Schema for completing a recurring task."""

    date: date
    skipped: bool = False
    notes: Optional[str] = None


class TaskCompletionResponse(BaseModel):
    """Schema for task completion in responses."""

    id: str
    recurring_task_id: str
    date: date
    completed_at: Optional[datetime] = None
    skipped: bool
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class RecurringTaskReorderRequest(BaseModel):
    """Schema for reordering recurring tasks."""

    task_ids: List[str]
