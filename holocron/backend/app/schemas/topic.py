from datetime import datetime

from pydantic import BaseModel


class TopicCreate(BaseModel):
    name: str
    description: str | None = None
    target_retention: float = 0.9


class TopicUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    target_retention: float | None = None


class TopicResponse(BaseModel):
    id: int
    name: str
    description: str | None
    target_retention: float
    created_at: datetime
    concept_count: int = 0
    mastery_pct: float = 0.0

    model_config = {"from_attributes": True}
