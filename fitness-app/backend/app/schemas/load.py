"""
Training-load Pydantic schemas (ARISE v3 spec §15.4).

Contract-mirror note: canonical shape for the iOS ``TrainingLoadResponse`` /
``LoadSeriesPoint`` structs in APITypes.swift (the Status LOAD strip).
"""
from typing import List, Optional

from pydantic import BaseModel


class LoadSeriesPoint(BaseModel):
    """One local day of the 28-day series."""
    local_date: str                  # YYYY-MM-DD
    run_load: float
    lift_load: float
    total_load: float
    miles: float
    run_acwr: Optional[float] = None  # null before 28 days of run history


class TrainingLoadResponse(BaseModel):
    """Response for GET /load."""
    as_of: str                       # YYYY-MM-DD (the client's local day)
    run_acute_7d: float
    run_chronic_28d: float
    run_acwr: Optional[float] = None  # null before 28 days of run history
    band: str                        # cold_start | ok | high | critical
    miles_7d: float
    miles_plan_7d: Optional[float] = None  # null without a campaign
    longest_run_7d: float
    flags: List[str]                 # subset of §6.3 flag names
    series: List[LoadSeriesPoint]    # 28 days, oldest first
