"""Notification schemas."""

from typing import Optional

from pydantic import BaseModel


class DeviceTokenRegister(BaseModel):
    """Schema for registering a Web Push subscription."""

    token: str  # Web Push subscription JSON (endpoint + keys)
    platform: str = "web"


class NotificationPreferenceUpdate(BaseModel):
    """Schema for updating notification preferences."""

    briefing_enabled: Optional[bool] = None
    briefing_time: Optional[str] = None  # "HH:MM" format
    task_reminders_enabled: Optional[bool] = None
