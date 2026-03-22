"""One-off reminder schemas."""

from datetime import datetime
from typing import Optional, Any, Dict

from pydantic import BaseModel

from app.models.enums import TriggerType, ReminderStatus


class ReminderCreate(BaseModel):
    """Schema for creating a one-off reminder."""

    title: str
    description: Optional[str] = None
    trigger_type: TriggerType
    trigger_config: Optional[Dict[str, Any]] = None
    source_action_item_id: Optional[str] = None


class ReminderUpdate(BaseModel):
    """Schema for updating a one-off reminder."""

    title: Optional[str] = None
    description: Optional[str] = None
    trigger_type: Optional[TriggerType] = None
    trigger_config: Optional[Dict[str, Any]] = None
    status: Optional[ReminderStatus] = None


class ReminderResponse(BaseModel):
    """Schema for reminder in responses."""

    id: str
    title: str
    description: Optional[str] = None
    trigger_type: str
    trigger_config: Optional[Dict[str, Any]] = None
    source_action_item_id: Optional[str] = None
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
