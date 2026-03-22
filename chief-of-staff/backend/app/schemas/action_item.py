"""Action item schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.enums import (
    ActionItemSource,
    ActionItemPriority,
    ActionItemStatus,
    DismissReason,
)


class ActionItemCreate(BaseModel):
    """Schema for creating an action item (manual or AI-extracted)."""

    source: ActionItemSource = ActionItemSource.MANUAL
    source_id: Optional[str] = None
    source_url: Optional[str] = None
    title: str
    description: Optional[str] = None
    extracted_deadline: Optional[datetime] = None
    confidence_score: Optional[float] = None
    priority: ActionItemPriority = ActionItemPriority.MEDIUM
    dedup_hash: Optional[str] = None


class ActionItemResponse(BaseModel):
    """Schema for action item in responses."""

    id: str
    source: str
    source_id: Optional[str] = None
    source_url: Optional[str] = None
    title: str
    description: Optional[str] = None
    extracted_deadline: Optional[datetime] = None
    confidence_score: Optional[float] = None
    priority: str
    status: str
    dismiss_reason: Optional[str] = None
    snoozed_until: Optional[datetime] = None
    linked_task_id: Optional[str] = None
    created_at: datetime
    actioned_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ActionItemDismiss(BaseModel):
    """Schema for dismissing an action item."""

    reason: DismissReason


class ActionItemSnooze(BaseModel):
    """Schema for snoozing an action item."""

    snoozed_until: datetime
