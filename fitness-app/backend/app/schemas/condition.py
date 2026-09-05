"""
Hunter Condition Pydantic schemas (ARISE v2 spec §4.3 / §13.1).

Contract-mirror note: these are the canonical shapes the iOS
``ConditionResponse`` / ``ConditionInput`` structs in APITypes.swift mirror.
"""
from typing import List, Optional

from pydantic import BaseModel

from app.schemas.cooldown import MuscleCooldownStatus


class ConditionInput(BaseModel):
    """One normalized Condition input with its post-renormalization weight."""
    # v3 §6.5: strain_yesterday → load_ratio (acute/chronic total load);
    # hrv_trend added (recovery's weight is 0.30 when it is present).
    key: str            # recovery | cooldowns | sleep | load_ratio | rhr_trend | hrv_trend
    label: str
    raw: Optional[float] = None
    subscore: Optional[int] = None   # None when unavailable
    weight: float
    effective_weight: float          # post-renormalization; 0.0 when unavailable
    available: bool
    source: Optional[str] = None     # whoop | apple_watch | app


class ConditionResponse(BaseModel):
    """Response for GET /condition."""
    score: int                       # 0-100
    band: str                        # peak | battle_ready | strained | critical
    generated_at: str                # ISO8601
    inputs: List[ConditionInput]
    muscles_cooling: List[MuscleCooldownStatus]
