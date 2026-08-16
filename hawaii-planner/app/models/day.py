"""TripDay and ScheduleItem. Times are Hawaii-local wall-clock; computed
timeline values are never persisted (derived on every read)."""
import uuid
from datetime import datetime, time

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class TripDay(Base):
    __tablename__ = "trip_days"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    # Nullable so generic "Day N" planning works before dates lock.
    date = Column(Date, nullable=True, unique=True)
    label = Column(String, nullable=True)
    start_time = Column(Time, nullable=False, default=time(8, 30))
    end_time = Column(Time, nullable=False, default=time(21, 30))
    notes = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    items = relationship(
        "ScheduleItem",
        cascade="all, delete-orphan",
        backref="day",
        order_by="ScheduleItem.position",
    )


class ScheduleItem(Base):
    """A stop on a day: either a pool idea (idea_id) or a one-off free-text
    entry — exactly one of the two, enforced by check constraint."""

    __tablename__ = "schedule_items"
    __table_args__ = (
        CheckConstraint(
            "(idea_id IS NULL) != (free_text_title IS NULL)",
            name="ck_item_idea_xor_free_text",
        ),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    trip_day_id = Column(
        String, ForeignKey("trip_days.id", ondelete="CASCADE"), nullable=False
    )
    idea_id = Column(
        String, ForeignKey("ideas.id", ondelete="CASCADE"), nullable=True
    )
    free_text_title = Column(String, nullable=True)
    # Free-text stops may carry a region; when null the timeline treats the
    # stop as staying in the previous stop's region.
    free_text_region_id = Column(String, ForeignKey("regions.id"), nullable=True)
    position = Column(Integer, nullable=False, default=0)
    duration_override_min = Column(Integer, nullable=True)
    # Pins a reservation: the cascade restarts from this wall-clock start.
    fixed_start_time = Column(Time, nullable=True)
    # Replaces the matrix+buffer figure for this stop's inbound leg.
    drive_override_min = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
