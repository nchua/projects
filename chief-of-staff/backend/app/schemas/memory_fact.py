"""Memory fact schemas for API request/response."""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field


class MemoryFactCreate(BaseModel):
    """Schema for manually creating a memory fact."""

    fact_text: str = Field(..., max_length=500)
    fact_type: str = Field(
        default="context",
        description="One of: commitment, deadline, decision, context, follow_up",
    )
    people: Optional[List[str]] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    importance: float = Field(default=0.5, ge=0.0, le=1.0)


class MemoryFactResponse(BaseModel):
    """Schema for memory fact in responses."""

    id: str
    fact_text: str
    fact_type: str
    source: str
    source_id: Optional[str] = None
    source_url: Optional[str] = None
    people: Optional[List[str]] = None
    valid_from: datetime
    valid_until: Optional[datetime] = None
    extracted_at: datetime
    importance: float
    access_count: int
    is_active: bool
    confidence: float
    created_at: datetime

    model_config = {"from_attributes": True}
