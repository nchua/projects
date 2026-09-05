"""
Campaign models (ARISE v3 spec §4) — the program as a first-class object.

Campaign → CampaignArc → HuntTemplate is the imported plan's *shape*;
PlannedHunt is a template materialized onto a calendar date with a
prescription (§5) and the guard's rationale (§6.4) attached.
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class CampaignStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class CampaignSource(str, enum.Enum):
    IMPORT = "import"
    TEMPLATE = "template"


class HuntType(str, enum.Enum):
    LIFT = "lift"
    RUN = "run"
    LIGHT = "light"
    REST = "rest"


class PlannedHuntStatus(str, enum.Enum):
    PLANNED = "planned"
    DONE = "done"
    MODIFIED = "modified"
    SKIPPED = "skipped"
    MOVED = "moved"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Campaign(Base):
    """A multi-month program with a goal (the PWA's whole ``PHASES`` array)."""
    __tablename__ = "campaigns"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    goal = Column(Text, nullable=True)
    start_date = Column(Date, nullable=False)
    status = Column(String, nullable=False, default=CampaignStatus.ACTIVE.value)
    source = Column(String, nullable=False, default=CampaignSource.IMPORT.value)
    # The Coach's accepted adjustments persist here (spec §8.4):
    # {"progression": {family: increment}, "reps": {family: {"sets": n, "reps": [lo, hi]}},
    #  "week_miles": {"YYYY-MM-DD": miles}, "deload_weeks": ["YYYY-MM-DD"],
    #  "last_deload_week": "YYYY-MM-DD"}
    overrides = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    arcs = relationship(
        "CampaignArc",
        back_populates="campaign",
        cascade="all, delete-orphan",
        order_by="CampaignArc.index",
    )
    planned_hunts = relationship("PlannedHunt", back_populates="campaign")
    goals = relationship("Goal", back_populates="campaign")


class CampaignArc(Base):
    """A block with its own mileage band and emphasis (one PWA phase)."""
    __tablename__ = "campaign_arcs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    campaign_id = Column(
        String, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    index = Column("index", Integer, nullable=False)
    name = Column(String, nullable=False)
    weeks = Column(Integer, nullable=False)
    run_miles_min = Column(Float, nullable=True)
    run_miles_max = Column(Float, nullable=True)
    long_run_miles = Column(Float, nullable=True)
    deload_every_n_weeks = Column(Integer, nullable=False, default=4, server_default="4")
    deload_factor = Column(Float, nullable=False, default=0.75, server_default="0.75")
    notes = Column(Text, nullable=True)

    campaign = relationship("Campaign", back_populates="arcs")
    templates = relationship(
        "HuntTemplate",
        back_populates="arc",
        cascade="all, delete-orphan",
        order_by="HuntTemplate.weekday",
    )
    planned_hunts = relationship("PlannedHunt", back_populates="arc")


class HuntTemplate(Base):
    """A weekday's session shape inside an arc (one PWA ``days[]`` entry)."""
    __tablename__ = "hunt_templates"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    arc_id = Column(
        String, ForeignKey("campaign_arcs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    weekday = Column(Integer, nullable=False)  # 0 = Monday … 6 = Sunday
    type = Column(String, nullable=False)      # HuntType value
    title = Column(String, nullable=False)
    location_tag = Column(String, nullable=True)
    load_hint = Column(Integer, nullable=True)  # 0-100
    # Spec §4.2 item shape: [{"family", "alternatives", "sets", "reps", "role",
    # "progression", "increment_lb", "rpe_cap"} | {"run", "miles"} | {"note"}]
    items = Column(JSON, nullable=False, default=list)
    note = Column(Text, nullable=True)

    arc = relationship("CampaignArc", back_populates="templates")
    planned_hunts = relationship("PlannedHunt", back_populates="template")


class PlannedHunt(Base):
    """A template materialized onto a calendar date, with a prescription."""
    __tablename__ = "planned_hunts"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "date", "template_id", name="uq_planned_hunts_user_date_template"
        ),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    campaign_id = Column(
        String, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    arc_id = Column(String, ForeignKey("campaign_arcs.id", ondelete="CASCADE"), nullable=False)
    template_id = Column(
        String, ForeignKey("hunt_templates.id", ondelete="CASCADE"), nullable=False
    )

    date = Column(Date, nullable=False, index=True)   # the user's local day
    week_start = Column(Date, nullable=False)         # Monday of that week
    # The arc ramp value for this week; the load service reads it as miles_plan_7d.
    week_target_miles = Column(Float, nullable=True)

    status = Column(String, nullable=False, default=PlannedHuntStatus.PLANNED.value)
    session_id = Column(
        String, ForeignKey("workout_sessions.id", ondelete="SET NULL"), nullable=True
    )
    moved_to = Column(Date, nullable=True)

    prescription = Column(JSON, nullable=True)
    prescription_version = Column(Integer, nullable=True)
    generated_at = Column(DateTime, nullable=True)
    rationale = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    campaign = relationship("Campaign", back_populates="planned_hunts")
    arc = relationship("CampaignArc", back_populates="planned_hunts")
    template = relationship("HuntTemplate", back_populates="planned_hunts")
    session = relationship("WorkoutSession")
