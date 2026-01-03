"""
Exercise schemas for request/response validation
"""
from pydantic import BaseModel, Field
from typing import Optional, List


class ExerciseCreate(BaseModel):
    """Schema for creating a custom exercise"""
    name: str = Field(..., min_length=1, max_length=100)
    category: Optional[str] = Field(None, pattern="^(Push|Pull|Legs|Core|Accessories)$")
    primary_muscle: Optional[str] = None
    secondary_muscles: Optional[List[str]] = None


class ExerciseResponse(BaseModel):
    """Schema for exercise information in responses"""
    id: str
    name: str
    canonical_id: Optional[str]
    category: Optional[str]
    primary_muscle: Optional[str]
    secondary_muscles: Optional[List[str]]
    is_custom: bool
    user_id: Optional[str]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True
