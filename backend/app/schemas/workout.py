"""
Workout schemas for request/response validation
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from app.models.workout import WeightUnit


class SetCreate(BaseModel):
    """Schema for creating a set"""
    weight: float = Field(..., gt=0, description="Weight lifted")
    weight_unit: WeightUnit = Field(default=WeightUnit.LB, description="Weight unit (lb or kg)")
    reps: int = Field(..., gt=0, le=100, description="Number of reps")
    rpe: Optional[int] = Field(None, ge=1, le=10, description="Rate of Perceived Exertion (1-10)")
    rir: Optional[int] = Field(None, ge=0, le=5, description="Reps in Reserve (0-5)")
    set_number: int = Field(..., ge=1, description="Set number/order")


class SetResponse(BaseModel):
    """Schema for set information in responses"""
    id: str
    weight: float
    weight_unit: str
    reps: int
    rpe: Optional[int]
    rir: Optional[int]
    set_number: int
    e1rm: Optional[float]
    created_at: str

    class Config:
        from_attributes = True


class WorkoutExerciseCreate(BaseModel):
    """Schema for creating an exercise within a workout"""
    exercise_id: str = Field(..., description="Exercise ID from library")
    order_index: int = Field(..., ge=0, description="Order of exercise in workout")
    sets: List[SetCreate] = Field(..., min_length=1, description="Sets for this exercise")


class WorkoutExerciseResponse(BaseModel):
    """Schema for workout exercise in responses"""
    id: str
    exercise_id: str
    exercise_name: str
    order_index: int
    sets: List[SetResponse]
    created_at: str

    class Config:
        from_attributes = True


class WorkoutCreate(BaseModel):
    """Schema for creating a workout"""
    date: datetime = Field(default_factory=datetime.utcnow, description="Workout date/time")
    duration_minutes: Optional[int] = Field(None, ge=1, le=600, description="Workout duration in minutes")
    session_rpe: Optional[int] = Field(None, ge=1, le=10, description="Overall session RPE")
    notes: Optional[str] = Field(None, max_length=1000, description="Workout notes")
    exercises: List[WorkoutExerciseCreate] = Field(..., min_length=1, description="Exercises in workout")


class WorkoutResponse(BaseModel):
    """Schema for workout information in responses"""
    id: str
    user_id: str
    date: str
    duration_minutes: Optional[int]
    session_rpe: Optional[int]
    notes: Optional[str]
    exercises: List[WorkoutExerciseResponse]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class WorkoutUpdate(BaseModel):
    """Schema for updating a workout"""
    date: Optional[datetime] = Field(None, description="Workout date/time")
    duration_minutes: Optional[int] = Field(None, ge=1, le=600, description="Workout duration in minutes")
    session_rpe: Optional[int] = Field(None, ge=1, le=10, description="Overall session RPE")
    notes: Optional[str] = Field(None, max_length=1000, description="Workout notes")
    exercises: Optional[List[WorkoutExerciseCreate]] = Field(None, min_length=1, description="Exercises in workout")


class WorkoutSummary(BaseModel):
    """Schema for workout summary (list view)"""
    id: str
    user_id: str
    date: str
    duration_minutes: Optional[int]
    session_rpe: Optional[int]
    notes: Optional[str]
    exercise_count: int
    total_sets: int
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True
