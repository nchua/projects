"""Auth-related Pydantic schemas."""

from zoneinfo import available_timezones

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.user import UserResponse


class RegisterRequest(BaseModel):
    """Request body for POST /auth/register."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=100)
    timezone: str = "America/Los_Angeles"

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        """Timezone must be a valid IANA timezone string."""
        if v not in available_timezones():
            raise ValueError(f"Invalid timezone: {v}")
        return v


class LoginRequest(BaseModel):
    """Request body for POST /auth/login."""

    email: EmailStr
    password: str


class AppleAuthRequest(BaseModel):
    """Request body for POST /auth/apple."""

    identity_token: str
    authorization_code: str
    display_name: str | None = Field(default=None, max_length=100)


class RefreshTokenRequest(BaseModel):
    """Request body for POST /auth/refresh."""

    refresh_token: str


class AuthResponse(BaseModel):
    """Response for all auth endpoints (register, login, apple, refresh)."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse
