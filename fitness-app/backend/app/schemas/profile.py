"""
User profile schemas for request/response validation
"""
from pydantic import BaseModel, Field
from typing import Optional
from app.models.user import TrainingExperience, WeightUnit, E1RMFormula


class ProfileUpdate(BaseModel):
    """Schema for updating user profile"""
    age: Optional[int] = Field(None, ge=13, le=120)
    sex: Optional[str] = Field(None, pattern="^[MF]$")
    bodyweight_lb: Optional[float] = Field(None, gt=0, le=1000)
    height_inches: Optional[float] = Field(None, gt=0, le=120)  # Max ~10 feet
    training_experience: Optional[TrainingExperience] = None
    preferred_unit: Optional[WeightUnit] = None
    e1rm_formula: Optional[E1RMFormula] = None


class ProfileResponse(BaseModel):
    """Schema for profile information in responses"""
    id: str
    user_id: str
    age: Optional[int]
    sex: Optional[str]
    bodyweight_lb: Optional[float]
    height_inches: Optional[float]
    training_experience: str
    preferred_unit: str
    e1rm_formula: str
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True
