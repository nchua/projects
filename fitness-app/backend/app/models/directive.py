"""
System Directive model — one line from the System per day (ARISE v2 spec §5).

Replaces the daily-quest system: a single server-generated directive per
(user, local day), persisted so the day's message is deterministic. Completion
is auto-detected (no claim step) — on workout create for types 2-7, or on
next-day generation for the rest directive.
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)

from app.core.database import Base

DIRECTIVE_XP_REWARD = 40


class DirectiveType(str, enum.Enum):
    """Directive rule types, in spec §5.2 priority order (first match wins)."""
    REST = "rest"                      # 1 — Condition CRITICAL
    STREAK_SAVE = "streak_save"        # 2 — streak lapses today
    RECLAIM_VOLUME = "reclaim_volume"  # 3 — muscle cleared, lift volume down
    BREAK_PLATEAU = "break_plateau"    # 4 — PLATEAU insight on a big-three lift
    FREQUENCY = "frequency"            # 5 — VOLUME_LOW insight
    GATE_REMINDER = "gate_reminder"    # 6 — open Gate exists (Phase 2)
    MAINTAIN = "maintain"              # 7 — default


class UserDirective(Base):
    """The System's daily directive for a user."""
    __tablename__ = "user_directives"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    date = Column(Date, nullable=False)  # user-local day (client_date)
    directive_type = Column(String, nullable=False)  # DirectiveType enum value
    message = Column(String, nullable=False)
    # Type-specific inputs captured at generation time (lift, muscle,
    # delta_pct, target_sets, ...) so the "why" sheet and completion checks
    # are deterministic. JSON precedent: WorkoutSession.hr_zone_seconds.
    params = Column(JSON, nullable=True)

    xp_reward = Column(Integer, default=DIRECTIVE_XP_REWARD, nullable=False)
    is_completed = Column(Boolean, default=False, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "date", name="unique_user_directive_date"),
    )
