"""
Daily training-load series (ARISE v3 spec §6.2).

One row per (user, local day). Recomputed for the trailing 35 days on every
ingest path and on ``GET /load`` by ``training_load_service`` (W2). Acute /
chronic values are 7- and 28-day EWMAs; ACWR is computed on run load only.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    String,
    UniqueConstraint,
)

from app.core.database import Base


class DailyTrainingLoad(Base):
    __tablename__ = "daily_training_load"
    __table_args__ = (
        UniqueConstraint("user_id", "local_date", name="uq_daily_training_load_user_date"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    local_date = Column(Date, nullable=False)

    run_load = Column(Float, nullable=False, default=0.0)
    lift_load = Column(Float, nullable=False, default=0.0)
    total_load = Column(Float, nullable=False, default=0.0)
    miles = Column(Float, nullable=False, default=0.0)

    run_acute_7d = Column(Float, nullable=True)
    run_chronic_28d = Column(Float, nullable=True)
    run_acwr = Column(Float, nullable=True)
    total_acute_7d = Column(Float, nullable=True)
    total_chronic_28d = Column(Float, nullable=True)
    total_acwr = Column(Float, nullable=True)

    miles_7d = Column(Float, nullable=False, default=0.0)
    miles_plan_7d = Column(Float, nullable=True)
    longest_run_7d = Column(Float, nullable=False, default=0.0)

    flags = Column(JSON, nullable=False, default=list)
    computed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
