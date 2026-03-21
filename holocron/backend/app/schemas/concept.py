from datetime import datetime

from pydantic import BaseModel

from app.models.concept import ConceptTier


class ConceptCreate(BaseModel):
    topic_id: int
    name: str
    description: str | None = None


class ConceptUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class ConceptResponse(BaseModel):
    id: int
    topic_id: int
    name: str
    description: str | None
    mastery_score: float
    tier: ConceptTier
    created_at: datetime
    unit_count: int = 0

    model_config = {"from_attributes": True}
