"""Shared schemas used across multiple endpoints."""

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standard error response body."""

    detail: str
    code: str
    field: str | None = None


class PaginationParams(BaseModel):
    """Query parameters for paginated list endpoints."""

    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
