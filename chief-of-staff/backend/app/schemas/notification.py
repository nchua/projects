"""Notification schemas."""

from typing import Optional

from pydantic import BaseModel


class DeviceTokenRegister(BaseModel):
    """Schema for registering an APNs device token."""

    token: str
    platform: str = "ios"


class NotificationPreferenceUpdate(BaseModel):
    """Schema for updating notification preferences."""

    briefing_enabled: Optional[bool] = None
    briefing_time: Optional[str] = None  # "HH:MM" format
    task_reminders_enabled: Optional[bool] = None
