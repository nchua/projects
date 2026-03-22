"""Device token Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RegisterDeviceTokenRequest(BaseModel):
    """Request body for POST /device-tokens."""

    token: str = Field(max_length=500)
    platform: str = Field(default="ios", pattern="^(ios|android)$")


class UnregisterDeviceTokenRequest(BaseModel):
    """Request body for DELETE /device-tokens."""

    token: str


class DeviceTokenResponse(BaseModel):
    """Response body for device token endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    token: str
    platform: str
    is_active: bool
    created_at: datetime
