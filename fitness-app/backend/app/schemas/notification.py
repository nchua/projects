"""
Pydantic schemas for push notification endpoints
"""
from pydantic import BaseModel, Field
from typing import List, Optional


class DeviceTokenRegister(BaseModel):
    """Register a device token for push notifications"""
    token: str = Field(..., description="APNs device token (hex string)")
    platform: str = Field(default="ios", description="Device platform")


class DeviceTokenResponse(BaseModel):
    """Response after registering a device token"""
    message: str


class NotificationPreferenceItem(BaseModel):
    """A single notification preference"""
    notification_type: str
    enabled: bool


class NotificationPreferenceUpdate(BaseModel):
    """Update a single notification preference"""
    notification_type: str
    enabled: bool


class NotificationPreferenceBulkUpdate(BaseModel):
    """Bulk update notification preferences"""
    preferences: List[NotificationPreferenceUpdate]


class NotificationPreferencesListResponse(BaseModel):
    """Response containing all notification preferences"""
    preferences: List[NotificationPreferenceItem]
