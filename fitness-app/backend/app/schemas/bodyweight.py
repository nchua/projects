"""
Bodyweight Pydantic schemas for request/response validation
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date as date_type
from enum import Enum


class WeightUnit(str, Enum):
    """Weight unit options"""
    LB = "lb"
    KG = "kg"


class BodyweightCreate(BaseModel):
    """Schema for creating/updating a bodyweight entry"""
    date: date_type = Field(..., description="Date of the weigh-in")
    weight: float = Field(..., gt=0, description="Body weight")
    weight_unit: WeightUnit = Field(default=WeightUnit.LB, description="Unit of weight measurement")
    source: Optional[str] = Field(default="manual", description="Source of entry (manual, apple_health, etc.)")


class BodyweightResponse(BaseModel):
    """Schema for bodyweight entry response"""
    id: str
    user_id: str
    date: str
    weight_lb: float
    weight_display: float  # Weight in user's preferred unit
    weight_unit: str
    source: str
    created_at: str
    updated_at: str


class BodyweightTrend(str, Enum):
    """Bodyweight trend direction"""
    GAINING = "gaining"
    LOSING = "losing"
    MAINTAINING = "maintaining"
    INSUFFICIENT_DATA = "insufficient_data"


class BodyweightHistoryResponse(BaseModel):
    """Schema for bodyweight history with analytics"""
    entries: List[BodyweightResponse]
    rolling_average_7day: Optional[float] = None
    rolling_average_14day: Optional[float] = None
    trend: BodyweightTrend = BodyweightTrend.INSUFFICIENT_DATA
    trend_rate_per_week: Optional[float] = None  # lbs per week
    is_plateau: bool = False  # Stable for 14+ days
    min_weight: Optional[float] = None
    max_weight: Optional[float] = None
    total_entries: int = 0
