"""
Activity/Health data Pydantic schemas for Apple HealthKit sync
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date as date_type
from enum import Enum


class ActivitySource(str, Enum):
    """Source of activity data"""
    APPLE_FITNESS = "apple_fitness"
    WHOOP = "whoop"
    GARMIN = "garmin"
    FITBIT = "fitbit"
    MANUAL = "manual"


class ActivityCreate(BaseModel):
    """Schema for creating/updating daily activity from HealthKit sync"""
    date: date_type = Field(..., description="Date of the activity")
    source: ActivitySource = Field(default=ActivitySource.APPLE_FITNESS, description="Source of activity data")

    # Core metrics (steps & calories)
    steps: Optional[int] = Field(None, ge=0, description="Total step count for the day")
    active_calories: Optional[int] = Field(None, ge=0, description="Active/exercise calories burned")
    total_calories: Optional[int] = Field(None, ge=0, description="Total daily calories burned (active + basal)")
    active_minutes: Optional[int] = Field(None, ge=0, description="Minutes of activity")

    # Apple Fitness rings
    exercise_minutes: Optional[int] = Field(None, ge=0, description="Exercise minutes (green ring)")
    stand_hours: Optional[int] = Field(None, ge=0, le=24, description="Stand hours (blue ring)")
    move_calories: Optional[int] = Field(None, ge=0, description="Move calories (red ring)")

    # Optional metrics from other sources (Whoop, etc.)
    strain: Optional[float] = Field(None, ge=0, le=21, description="Whoop strain score 0-21")
    recovery_score: Optional[int] = Field(None, ge=0, le=100, description="Recovery percentage")
    hrv: Optional[int] = Field(None, ge=0, description="Heart rate variability in ms")
    resting_heart_rate: Optional[int] = Field(None, ge=30, le=120, description="Resting heart rate")
    sleep_hours: Optional[float] = Field(None, ge=0, le=24, description="Hours of sleep")


class ActivityResponse(BaseModel):
    """Schema for activity entry response"""
    id: str
    user_id: str
    date: str
    source: str
    steps: Optional[int] = None
    active_calories: Optional[int] = None
    total_calories: Optional[int] = None
    active_minutes: Optional[int] = None
    exercise_minutes: Optional[int] = None
    stand_hours: Optional[int] = None
    move_calories: Optional[int] = None
    strain: Optional[float] = None
    recovery_score: Optional[int] = None
    hrv: Optional[int] = None
    resting_heart_rate: Optional[int] = None
    sleep_hours: Optional[float] = None
    created_at: str
    updated_at: str


class ActivityHistoryResponse(BaseModel):
    """Schema for activity history with pagination"""
    entries: List[ActivityResponse]
    total: int
    has_more: bool


class LastSyncResponse(BaseModel):
    """Schema for last sync info"""
    last_synced_date: Optional[str] = None
    source: str
