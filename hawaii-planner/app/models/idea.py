"""Idea — one table for both activities and restaurants (kind discriminator) —
and Vote, the single-select per-member reaction."""
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base

KIND_ACTIVITY = "activity"
KIND_RESTAURANT = "restaurant"

VOTE_INTERESTED = "interested"
VOTE_MUST_GO = "must_go"
VOTE_SCORES = {VOTE_INTERESTED: 1, VOTE_MUST_GO: 3}
MUST_GO_BUDGET_PER_BOARD = 3


class Idea(Base):
    __tablename__ = "ideas"
    __table_args__ = (
        CheckConstraint("kind IN ('activity', 'restaurant')", name="ck_idea_kind"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=False)
    kind = Column(String, nullable=False)
    region_id = Column(String, ForeignKey("regions.id"), nullable=False)
    duration_min = Column(Integer, nullable=False, default=90)
    yelp_url = Column(String, nullable=True)
    maps_url = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    # Source credit for seeded family recommendations ("Erica's mom's friends");
    # distinct from created_by, which is the app member who added it.
    recommended_by = Column(String, nullable=True)
    reservation_rule = Column(Text, nullable=True)
    closed_days = Column(String, nullable=False, default="")  # CSV: "mon,tue"
    difficulty = Column(String, nullable=True)
    best_time = Column(String, nullable=True)
    meal_tags = Column(String, nullable=False, default="")  # CSV: "lunch,treat"
    created_by_member_id = Column(String, ForeignKey("members.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    votes = relationship("Vote", cascade="all, delete-orphan", backref="idea")
    schedule_items = relationship(
        "ScheduleItem", cascade="all, delete-orphan", backref="idea"
    )


class Vote(Base):
    """One reaction per member per idea; existence + value, toggled via PUT/DELETE."""

    __tablename__ = "votes"
    __table_args__ = (
        CheckConstraint("value IN ('interested', 'must_go')", name="ck_vote_value"),
    )

    idea_id = Column(
        String, ForeignKey("ideas.id", ondelete="CASCADE"), primary_key=True
    )
    member_id = Column(
        String, ForeignKey("members.id", ondelete="CASCADE"), primary_key=True
    )
    value = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
