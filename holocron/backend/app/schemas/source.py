from datetime import datetime

from pydantic import BaseModel

from app.models.source import SourceType


class SourceCreate(BaseModel):
    type: SourceType
    name: str
    uri: str | None = None


class SourceResponse(BaseModel):
    id: int
    type: SourceType
    uri: str | None
    name: str
    last_synced_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
