from datetime import datetime

from pydantic import BaseModel

from app.models.review import Rating


class ReviewCreate(BaseModel):
    learning_unit_id: int
    rating: Rating
    time_to_reveal_ms: int | None = None
    time_reading_ms: int | None = None


class ReviewResponse(BaseModel):
    id: int
    learning_unit_id: int
    rating: Rating
    time_to_reveal_ms: int | None
    time_reading_ms: int | None
    reviewed_at: datetime
    next_review_at: datetime | None  # new schedule after this review

    model_config = {"from_attributes": True}


class SessionSummary(BaseModel):
    """Post-session stats."""

    total_reviewed: int
    recalled: int  # got_it + easy
    struggled: int
    forgot: int
    session_duration_seconds: int | None = None
    strongest_topic: str | None = None
    weakest_topic: str | None = None
