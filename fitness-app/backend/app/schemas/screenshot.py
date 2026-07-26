"""
Screenshot processing schemas for request/response validation
"""
from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


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


class HeartRateZone(BaseModel):
    """Schema for heart rate zone data from WHOOP"""
    zone: Optional[int] = Field(None, description="Zone number (0-5)")
    bpm_range: Optional[str] = Field(None, description="BPM range (e.g., '93-111')")
    percentage: Optional[float] = Field(None, description="Percentage of time in zone")
    duration: Optional[str] = Field(None, description="Time in zone (e.g., '15:30')")


class ScreenshotProcessResponse(BaseModel):
    """Schema for screenshot processing response"""
    # Screenshot type indicator
    screenshot_type: str = Field(default="gym_workout", description="Type: gym_workout or whoop_activity")

    # Common fields
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
    activity_id: Optional[str] = Field(None, description="Created activity ID if saved (WHOOP)")
    activity_saved: bool = Field(default=False, description="Whether activity was saved (WHOOP)")

    # WHOOP/Activity-specific fields
    activity_type: Optional[str] = Field(None, description="Activity type (e.g., 'TENNIS', 'RUNNING')")
    time_range: Optional[str] = Field(None, description="Activity time range (e.g., '7:03 PM to 8:46 PM')")
    strain: Optional[float] = Field(None, description="WHOOP activity strain score")
    steps: Optional[int] = Field(None, description="Step count")
    calories: Optional[int] = Field(None, description="Calories burned")
    avg_hr: Optional[int] = Field(None, description="Average heart rate in BPM")
    max_hr: Optional[int] = Field(None, description="Max heart rate in BPM")
    source: Optional[str] = Field(None, description="Data source (e.g., 'VIA APPLE WATCH')")
    heart_rate_zones: List[HeartRateZone] = Field(default_factory=list, description="Heart rate zone breakdown")
    # Cardio metrics as displayed on the screenshot (source units). The client
    # shows these in the edit-before-save flow and posts them back unchanged.
    active_calories: Optional[int] = Field(None, description="Active/move calories")
    total_calories: Optional[int] = Field(None, description="Total calories")
    distance: Optional[float] = Field(None, description="Distance in distance_unit")
    distance_unit: Optional[str] = Field(None, description="mi | km | m")
    avg_pace: Optional[str] = Field(None, description="Average pace, e.g. 9'19\"")
    pace_unit: Optional[str] = Field(None, description="/mi | /km")
    avg_speed: Optional[float] = Field(None, description="Average speed in speed_unit")
    speed_unit: Optional[str] = Field(None, description="mph | kph")
    elevation_gain: Optional[float] = Field(None, description="Elevation gain in elevation_unit")
    elevation_unit: Optional[str] = Field(None, description="ft | m")
    avg_cadence: Optional[int] = Field(None, description="Average cadence (steps/min)")
    avg_power: Optional[int] = Field(None, description="Average power (watts)")

    class Config:
        from_attributes = True


class ActivitySaveRequest(BaseModel):
    """Save an (optionally user-edited) activity extraction (ARISE v2 §7.3).

    Manual-controls flow: the client processes the screenshot with
    save_activity=false, lets the user edit duration and avg/max HR, then
    posts the edited fields here.
    """
    activity_type: Optional[str] = Field(None, description="Activity type (e.g., 'TENNIS')")
    session_date: Optional[str] = Field(None, description="Activity date (YYYY-MM-DD)")
    time_range: Optional[str] = Field(None, description="Activity time range")
    duration_minutes: Optional[int] = Field(None, ge=1, le=1440)
    strain: Optional[float] = Field(None, ge=0, le=21, description="WHOOP strain (never converted)")
    steps: Optional[int] = Field(None, ge=0)
    calories: Optional[int] = Field(None, ge=0)
    avg_hr: Optional[int] = Field(None, ge=20, le=250)
    max_hr: Optional[int] = Field(None, ge=20, le=250)
    heart_rate_zones: List[HeartRateZone] = Field(default_factory=list)
    # Cardio metrics, echoed back in the source's own units so the edit flow
    # preserves what the screenshot showed. Normalized to SI on save.
    active_calories: Optional[int] = Field(None, ge=0)
    total_calories: Optional[int] = Field(None, ge=0)
    distance: Optional[float] = Field(None, ge=0)
    distance_unit: Optional[str] = None
    avg_pace: Optional[str] = None
    pace_unit: Optional[str] = None
    avg_speed: Optional[float] = Field(None, ge=0)
    speed_unit: Optional[str] = None
    elevation_gain: Optional[float] = None
    elevation_unit: Optional[str] = None
    avg_cadence: Optional[int] = Field(None, ge=0)
    avg_power: Optional[int] = Field(None, ge=0)


class ActivitySaveResponse(BaseModel):
    """Response for POST /screenshot/save-activity."""
    activity_id: str
    workout_id: str
    activity_saved: bool = True


class ScreenshotBatchResponse(BaseModel):
    """Response for batch screenshot processing"""
    screenshots_processed: int = Field(..., description="Number of screenshots processed")
    screenshot_type: str = Field(default="gym_workout", description="Type: gym_workout or whoop_activity")
    session_date: Optional[str] = Field(None, description="Combined session date")
    session_name: Optional[str] = Field(None, description="Combined session name")
    duration_minutes: Optional[int] = Field(None, description="Total duration")
    summary: Optional[Dict[str, Any]] = Field(None, description="Combined summary stats")
    exercises: List[ExtractedExercise] = Field(default_factory=list, description="All extracted exercises")
    processing_confidence: str = Field(default="medium", description="Overall confidence")
    workout_id: Optional[str] = Field(None, description="Created workout ID if saved")
    workout_saved: bool = Field(default=False, description="Whether workout was saved")
    activity_id: Optional[str] = Field(None, description="Created activity ID if saved (WHOOP)")
    activity_saved: bool = Field(default=False, description="Whether activity was saved (WHOOP)")

    # WHOOP/Activity-specific fields
    activity_type: Optional[str] = Field(None, description="Activity type (e.g., 'TENNIS', 'RUNNING')")
    time_range: Optional[str] = Field(None, description="Activity time range")
    strain: Optional[float] = Field(None, description="WHOOP activity strain score")
    steps: Optional[int] = Field(None, description="Step count")
    calories: Optional[int] = Field(None, description="Calories burned")
    avg_hr: Optional[int] = Field(None, description="Average heart rate in BPM")
    max_hr: Optional[int] = Field(None, description="Max heart rate in BPM")
    source: Optional[str] = Field(None, description="Data source")
    heart_rate_zones: List[HeartRateZone] = Field(default_factory=list, description="Heart rate zone breakdown")
    # Cardio metrics as displayed on the screenshot (source units). The client
    # shows these in the edit-before-save flow and posts them back unchanged.
    active_calories: Optional[int] = Field(None, description="Active/move calories")
    total_calories: Optional[int] = Field(None, description="Total calories")
    distance: Optional[float] = Field(None, description="Distance in distance_unit")
    distance_unit: Optional[str] = Field(None, description="mi | km | m")
    avg_pace: Optional[str] = Field(None, description="Average pace, e.g. 9'19\"")
    pace_unit: Optional[str] = Field(None, description="/mi | /km")
    avg_speed: Optional[float] = Field(None, description="Average speed in speed_unit")
    speed_unit: Optional[str] = Field(None, description="mph | kph")
    elevation_gain: Optional[float] = Field(None, description="Elevation gain in elevation_unit")
    elevation_unit: Optional[str] = Field(None, description="ft | m")
    avg_cadence: Optional[int] = Field(None, description="Average cadence (steps/min)")
    avg_power: Optional[int] = Field(None, description="Average power (watts)")

    class Config:
        from_attributes = True
