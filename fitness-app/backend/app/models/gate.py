"""
PR Gate model (ARISE v2 spec §6) — Dungeons reborn as boss fights the data
says you can win.

A Gate is a time-boxed PR attempt on a specific lift, spawned only when the
trend engine projects a PR inside the window AND Condition is BATTLE READY+.
Fully generated from the user's own data — no definition tables.
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String

from app.core.database import Base


class GateStatus(str, enum.Enum):
    """Lifecycle (spec §6.4): open → active → cleared | expired."""
    OPEN = "open"          # spawned, visible, not yet accepted
    ACTIVE = "active"      # user tapped ACCEPT GATE (commitment marker only)
    CLEARED = "cleared"    # a set hit target_e1rm — XP awarded, no claim step
    EXPIRED = "expired"    # window passed — quiet, no penalty


class GateRank(str, enum.Enum):
    """Rank encodes the size of the e1RM jump (spec §6.3)."""
    C = "C"
    B = "B"
    A = "A"
    S = "S"


class PRGate(Base):
    """A spawned PR Gate (spec §6.5)."""
    __tablename__ = "pr_gates"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    # Canonical root exercise id for the lift (aliases resolve to this).
    exercise_id = Column(String, ForeignKey("exercises.id"), nullable=False)

    rank = Column(String, nullable=False)           # GateRank value
    name = Column(String, nullable=False)           # "B-Rank Gate: Bench 225×4"

    target_weight = Column(Float, nullable=False)
    target_reps = Column(Integer, nullable=False)
    target_e1rm = Column(Float, nullable=False)
    baseline_e1rm = Column(Float, nullable=False)
    projected_e1rm = Column(Float, nullable=False)
    weekly_slope = Column(Float, nullable=False)    # lb/week at spawn time
    condition_at_spawn = Column(Integer, nullable=False)

    status = Column(String, default=GateStatus.OPEN.value, nullable=False)
    spawned_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    accepted_at = Column(DateTime, nullable=True)
    cleared_at = Column(DateTime, nullable=True)
    cleared_by_set_id = Column(String, ForeignKey("sets.id"), nullable=True)
    xp_awarded = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_pr_gates_user_status", "user_id", "status"),
    )
