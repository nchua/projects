"""Integration schemas (never expose tokens)."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.enums import IntegrationProvider


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


class IntegrationHealthResponse(BaseModel):
    """Schema for integration health overview."""

    provider: str
    status: str
    last_synced_at: Optional[datetime] = None
    is_active: bool


class OAuthCallbackRequest(BaseModel):
    """Schema for OAuth callback data from the client."""

    provider: IntegrationProvider
    code: str
    redirect_uri: str
    state: str  # CSRF protection — must match the state from authorize
