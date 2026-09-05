"""
Campaign Pydantic schemas (ARISE v3 spec §4.3 / §4.5).

``CampaignImportRequest`` accepts the training-calendar PWA's ``data.js``
``PHASES`` array verbatim (``PhaseIn`` / ``PhaseDayIn``); the parser lives in
``campaign_service.parse_phase_item``.
"""
from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.schemas.goal import GoalCreate


class PhaseDayIn(BaseModel):
    """One ``days[]`` entry from data.js."""
    name: str                                   # "Monday" … "Sunday"
    type: str                                   # lift | run | light | rest
    title: str
    load: Optional[int] = None
    items: List[List[str]] = Field(default_factory=list)   # [[name, spec], …]
    note: Optional[str] = None


class PhaseIn(BaseModel):
    """One PWA phase — becomes a ``CampaignArc``."""
    key: Optional[str] = None
    label: str                                  # "Months 1–2"
    sub: Optional[str] = None
    milesMin: Optional[float] = None
    milesMax: Optional[float] = None
    longRunMi: Optional[float] = None
    note: Optional[str] = None
    days: List[PhaseDayIn] = Field(default_factory=list)


class CampaignImportRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    phases: List[PhaseIn] = Field(..., min_length=1)
    start_date: Optional[date] = None           # defaults to the Monday of client_date's week
    client_date: Optional[date] = None
    goal: Optional[str] = Field(None, max_length=500)
    objectives: List[GoalCreate] = Field(default_factory=list)
    replace: bool = False


class ArcCreate(BaseModel):
    name: str
    weeks: int = Field(8, ge=1, le=52)
    run_miles_min: Optional[float] = Field(None, ge=0)
    run_miles_max: Optional[float] = Field(None, ge=0)
    long_run_miles: Optional[float] = Field(None, ge=0)
    deload_every_n_weeks: int = Field(4, ge=2, le=12)
    deload_factor: float = Field(0.75, gt=0, le=1)
    notes: Optional[str] = None


class CampaignCreate(BaseModel):
    """POST /campaign — minimal manual create (no templates)."""
    name: str = Field(..., min_length=1, max_length=120)
    start_date: Optional[date] = None
    client_date: Optional[date] = None
    goal: Optional[str] = Field(None, max_length=500)
    arcs: List[ArcCreate] = Field(default_factory=list)


class ArcUpdate(BaseModel):
    id: str
    run_miles_min: Optional[float] = Field(None, ge=0)
    run_miles_max: Optional[float] = Field(None, ge=0)
    long_run_miles: Optional[float] = Field(None, ge=0)
    weeks: Optional[int] = Field(None, ge=1, le=52)


class CampaignUpdate(BaseModel):
    """PUT /campaign/{id} — status, name, arc mileage band edits."""
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    status: Optional[str] = None                # active | paused | completed
    goal: Optional[str] = Field(None, max_length=500)
    arcs: Optional[List[ArcUpdate]] = None
    client_date: Optional[date] = None


class HuntTemplateResponse(BaseModel):
    id: str
    weekday: int
    type: str
    title: str
    location_tag: Optional[str] = None
    load_hint: Optional[int] = None
    items: List[Dict[str, Any]] = Field(default_factory=list)
    note: Optional[str] = None


class ArcResponse(BaseModel):
    id: str
    index: int
    name: str
    weeks: int
    run_miles_min: Optional[float] = None
    run_miles_max: Optional[float] = None
    long_run_miles: Optional[float] = None
    deload_every_n_weeks: int
    deload_factor: float
    notes: Optional[str] = None
    start_date: str
    end_date: str
    templates: List[HuntTemplateResponse] = Field(default_factory=list)


class CampaignResponse(BaseModel):
    """GET /campaign/current — campaign + arcs + where we are (spec §4.5)."""
    id: str
    name: str
    goal: Optional[str] = None
    start_date: str
    end_date: str
    status: str
    source: str
    arcs: List[ArcResponse]
    current_arc_index: Optional[int] = None
    week_in_arc: Optional[int] = None          # 1-based
    campaign_week: Optional[int] = None        # 1-based across arcs
    deload_week: bool = False
    week_start: str
    week_target_miles: Optional[float] = None
    overrides: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class CampaignImportResponse(CampaignResponse):
    warnings: List[str] = Field(default_factory=list)
    templates_created: int = 0
    objectives_created: int = 0
