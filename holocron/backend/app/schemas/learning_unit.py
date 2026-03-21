from datetime import datetime

from pydantic import BaseModel

from app.models.learning_unit import UnitType


class LearningUnitCreate(BaseModel):
    concept_id: int
    type: UnitType = UnitType.CONCEPT
    front_content: str
    back_content: str
    source_id: int | None = None
    ai_generated: bool = False
    confidence_score: float | None = None  # if set, routes through inbox


class LearningUnitUpdate(BaseModel):
    front_content: str | None = None
    back_content: str | None = None


class LearningUnitResponse(BaseModel):
    id: int
    concept_id: int
    type: UnitType
    front_content: str
    back_content: str
    difficulty: float
    stability: float
    retrievability: float
    next_review_at: datetime | None
    review_count: int
    lapse_count: int
    ai_generated: bool
    auto_accepted: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewCardResponse(BaseModel):
    """Card ready for review — includes topic name for UI header."""

    id: int
    concept_id: int
    type: UnitType
    front_content: str
    back_content: str
    topic_name: str
    source_name: str | None = None
