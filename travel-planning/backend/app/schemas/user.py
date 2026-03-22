"""User-related Pydantic schemas."""

from datetime import datetime, time
from typing import Any
from uuid import UUID
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import TravelMode

VALID_BUFFER_VALUES = [0, 5, 10, 15, 20, 30, 45, 60]


class UserResponse(BaseModel):
    """Public user profile response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    display_name: str | None
    auth_provider: str
    default_buffer_minutes: int
    default_travel_mode: str
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    timezone: str
    created_at: datetime

    @field_validator("quiet_hours_start", "quiet_hours_end", mode="before")
    @classmethod
    def serialize_time(cls, v: Any) -> str | None:
        """Convert time objects to HH:MM strings."""
        if v is None:
            return None
        if isinstance(v, time):
            return v.strftime("%H:%M")
        return v

    @field_validator("auth_provider", "default_travel_mode", mode="before")
    @classmethod
    def serialize_enum(cls, v: Any) -> str:
        """Convert enum values to their string representation."""
        if hasattr(v, "value"):
            return v.value
        return str(v)


class UpdateUserRequest(BaseModel):
    """Request body for PATCH /users/me."""

    display_name: str | None = Field(default=None, max_length=100)
    default_buffer_minutes: int | None = None
    default_travel_mode: str | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    timezone: str | None = None

    @field_validator("default_buffer_minutes")
    @classmethod
    def validate_buffer(cls, v: int | None) -> int | None:
        """Buffer minutes must be one of the allowed values."""
        if v is not None and v not in VALID_BUFFER_VALUES:
            raise ValueError(
                f"default_buffer_minutes must be one of {VALID_BUFFER_VALUES}"
            )
        return v

    @field_validator("default_travel_mode")
    @classmethod
    def validate_travel_mode(cls, v: str | None) -> str | None:
        """Travel mode must be a valid TravelMode enum value."""
        if v is not None:
            valid = [m.value for m in TravelMode]
            if v not in valid:
                raise ValueError(
                    f"default_travel_mode must be one of {valid}"
                )
        return v

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str | None) -> str | None:
        """Timezone must be a valid IANA timezone string."""
        if v is not None and v not in available_timezones():
            raise ValueError(f"Invalid timezone: {v}")
        return v

    @model_validator(mode="after")
    def validate_quiet_hours(self) -> "UpdateUserRequest":
        """Quiet hours start and end must be set together or both null."""
        start = self.quiet_hours_start
        end = self.quiet_hours_end
        if (start is not None) != (end is not None):
            raise ValueError(
                "quiet_hours_start and quiet_hours_end "
                "must be set together or both null"
            )
        return self
