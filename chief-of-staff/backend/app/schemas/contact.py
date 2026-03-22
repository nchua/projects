"""Contact schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ContactCreate(BaseModel):
    """Schema for creating a contact."""

    display_name: str
    email: Optional[str] = None
    slack_id: Optional[str] = None
    github_username: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None


class ContactResponse(BaseModel):
    """Schema for contact in responses."""

    id: str
    display_name: str
    email: Optional[str] = None
    slack_id: Optional[str] = None
    github_username: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    last_interaction_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}
