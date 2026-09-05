"""
Coach output storage (ARISE v3 spec §8.5).

One row per (user, kind, for_date): the weekly Debrief or an answer. Token
counts are logged, not stored; "why did it say that" is the context hash plus
the candidate-ops snapshot inside ``validated``.
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, Date, DateTime, ForeignKey, String, UniqueConstraint

from app.core.database import Base


class CoachOutputKind(str, enum.Enum):
    DEBRIEF = "debrief"
    ANSWER = "answer"


class CoachOutputSource(str, enum.Enum):
    MODEL = "model"
    ENGINE_FALLBACK = "engine_fallback"


class CoachOutput(Base):
    __tablename__ = "coach_outputs"
    __table_args__ = (
        UniqueConstraint("user_id", "kind", "for_date", name="uq_coach_outputs_user_kind_date"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    kind = Column(String, nullable=False)          # CoachOutputKind value
    for_date = Column(Date, nullable=False)
    context_hash = Column(String, nullable=False)
    prompt_version = Column(String, nullable=False)
    model = Column(String, nullable=False)
    output = Column(JSON, nullable=True)
    validated = Column(JSON, nullable=True)
    decisions = Column(JSON, nullable=True)
    source = Column(String, nullable=False, default=CoachOutputSource.MODEL.value)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
