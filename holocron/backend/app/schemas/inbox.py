from datetime import datetime

from pydantic import BaseModel

from app.models.inbox import InboxStatus
from app.models.learning_unit import UnitType


class InboxItemResponse(BaseModel):
    id: int
    learning_unit_id: int
    confidence_score: float
    status: InboxStatus
    created_at: datetime
    # Inline card preview
    front_content: str
    back_content: str
    unit_type: UnitType
    source_name: str | None = None


class InboxAction(BaseModel):
    status: InboxStatus  # accepted or rejected
