"""
Screenshot processing schemas for request/response validation
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import date


class ExtractedSet(BaseModel):
    """Schema for a set extracted from screenshot"""
    weight_lb: float = Field(..., description="Weight in pounds")
    reps: int = Field(..., description="Number of reps")
    sets: int = Field(default=1, description="Number of sets at this weight/rep combo")
    is_warmup: bool = Field(default=False, description="Whether this is a warmup set")


class ScreenshotProcessOptions(BaseModel):
    """Options for screenshot processing"""
    save_workout: bool = Field(default=False, description="Auto-save extracted data as a workout")
    session_date: Optional[date] = Field(None, description="Override session date (defaults to today)")
    include_warmups: bool = Field(default=True, description="Include warmup sets in saved workout")


class ExtractedExercise(BaseModel):
    """Schema for an exercise extracted from screenshot"""
    name: str = Field(..., description="Exercise name as shown in screenshot")
    equipment: Optional[str] = Field(None, description="Equipment type (barbell, dumbbell, cable, etc.)")
    variation: Optional[str] = Field(None, description="Exercise variation (seated, incline, etc.)")
    sets: List[ExtractedSet] = Field(default_factory=list, description="Sets performed")
    total_reps: Optional[int] = Field(None, description="Total reps for this exercise")
    total_volume_lb: Optional[float] = Field(None, description="Total volume in pounds")

    # Matching results
    matched_exercise_id: Optional[str] = Field(None, description="Matched exercise ID from database")
    matched_exercise_name: Optional[str] = Field(None, description="Matched exercise name")
    match_confidence: Optional[int] = Field(None, description="Match confidence score (0-100)")


class ExtractedSummary(BaseModel):
    """Schema for workout summary extracted from screenshot"""
    tonnage_lb: Optional[float] = Field(None, description="Total weight lifted in pounds")
    total_reps: Optional[int] = Field(None, description="Total reps across all exercises")


class ScreenshotProcessResponse(BaseModel):
    """Schema for screenshot processing response"""
    session_date: Optional[str] = Field(None, description="Workout date (YYYY-MM-DD)")
    session_name: Optional[str] = Field(None, description="Workout name/title")
    duration_minutes: Optional[int] = Field(None, description="Workout duration in minutes")
    summary: Optional[Dict[str, Any]] = Field(None, description="Workout summary stats")
    exercises: List[ExtractedExercise] = Field(default_factory=list, description="Extracted exercises")
    processing_confidence: str = Field(
        default="medium",
        description="Overall processing confidence (high, medium, low)"
    )
    workout_id: Optional[str] = Field(None, description="Created workout ID if saved")
    workout_saved: bool = Field(default=False, description="Whether workout was saved")

    class Config:
        from_attributes = True


class ScreenshotBatchResponse(BaseModel):
    """Response for batch screenshot processing"""
    screenshots_processed: int = Field(..., description="Number of screenshots processed")
    session_date: Optional[str] = Field(None, description="Combined session date")
    session_name: Optional[str] = Field(None, description="Combined session name")
    duration_minutes: Optional[int] = Field(None, description="Total duration")
    summary: Optional[Dict[str, Any]] = Field(None, description="Combined summary stats")
    exercises: List[ExtractedExercise] = Field(default_factory=list, description="All extracted exercises")
    processing_confidence: str = Field(default="medium", description="Overall confidence")
    workout_id: Optional[str] = Field(None, description="Created workout ID if saved")
    workout_saved: bool = Field(default=False, description="Whether workout was saved")

    class Config:
        from_attributes = True
