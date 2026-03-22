"""Authentication schemas for request/response validation."""

from datetime import datetime, time
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserRegister(BaseModel):
    """Schema for user registration."""

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password strength."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class UserLogin(BaseModel):
    """Schema for user login."""

    email: EmailStr
    password: str


class Token(BaseModel):
    """Schema for JWT token response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefresh(BaseModel):
    """Schema for token refresh request."""

    refresh_token: str


class UserResponse(BaseModel):
    """Schema for user information in responses."""

    id: str
    email: str
    timezone: Optional[str] = None
    wake_time: Optional[str] = None
    sleep_time: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    """Schema for updating user settings."""

    timezone: Optional[str] = None
    wake_time: Optional[time] = None
    sleep_time: Optional[time] = None

    @field_validator("wake_time", "sleep_time", mode="before")
    @classmethod
    def parse_time_string(cls, v: str | time | None) -> time | None:
        """Accept 'HH:MM' strings and convert to datetime.time."""
        if v is None:
            return None
        if isinstance(v, time):
            return v
        try:
            parts = str(v).split(":")
            return time(int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            raise ValueError("Time must be in HH:MM format")
