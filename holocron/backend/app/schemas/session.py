"""Schemas for review sessions with pacing and interleaving."""

from pydantic import BaseModel

from app.models.learning_unit import UnitType
from app.services.session import SessionMode


class SessionCard(BaseModel):
    """A card in a paced review session."""

    id: int
    concept_id: int
    type: UnitType
    front_content: str
    back_content: str
    topic_name: str
    source_name: str | None = None
    phase: str  # warmup, core, challenge, cooldown


class SessionStartResponse(BaseModel):
    """Response when starting a review session."""

    cards: list[SessionCard]
    total_due: int          # total cards due (may exceed session size)
    session_size: int       # cards in this session
    estimated_minutes: int  # estimated session duration
    topics: list[str]       # topics covered in this session
    reviews_today: int      # reviews already completed today
    daily_cap: int          # daily review cap
    mode: SessionMode


class TopicPerformance(BaseModel):
    """Per-topic performance in a session."""

    topic_name: str
    total: int
    recalled: int
    struggled: int
    forgot: int
    accuracy: float  # recalled / total


class SessionSummaryResponse(BaseModel):
    """Enhanced post-session summary with per-topic breakdowns."""

    total_reviewed: int
    recalled: int
    struggled: int
    forgot: int
    session_duration_seconds: int | None = None
    strongest_topic: str | None = None
    weakest_topic: str | None = None
    topic_performance: list[TopicPerformance] = []
