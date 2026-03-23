"""Integration schemas (never expose tokens)."""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, field_validator

from app.models.enums import IntegrationProvider


def _ensure_utc(v: datetime | None) -> datetime | None:
    """Treat naive datetimes (from SQLite) as UTC so JSON includes +00:00."""
    if v is not None and v.tzinfo is None:
        return v.replace(tzinfo=timezone.utc)
    return v


class IntegrationResponse(BaseModel):
    """Schema for integration in responses. Tokens are never exposed."""

    id: str
    provider: str
    scopes: Optional[str] = None
    status: str
    error_count: int
    last_error: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("last_synced_at", "created_at", mode="before")
    @classmethod
    def ensure_utc(cls, v: datetime | None) -> datetime | None:
        return _ensure_utc(v)


class IntegrationHealthResponse(BaseModel):
    """Schema for integration health overview."""

    provider: str
    status: str
    last_synced_at: Optional[datetime] = None
    is_active: bool

    @field_validator("last_synced_at", mode="before")
    @classmethod
    def ensure_utc(cls, v: datetime | None) -> datetime | None:
        return _ensure_utc(v)


class AppleCalendarConfigureRequest(BaseModel):
    """Schema for Apple Calendar configuration."""

    calendars: Optional[list[str]] = None


class OAuthCallbackRequest(BaseModel):
    """Schema for OAuth callback data from the client."""

    provider: IntegrationProvider
    code: str
    redirect_uri: str
    state: str  # CSRF protection — must match the state from authorize
