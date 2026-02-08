"""
Weekly Progress Report schemas for goal-vs-actual comparison with pace prediction
"""
from pydantic import BaseModel
from typing import Optional, List
from enum import Enum

from app.schemas.analytics import PRResponse
from app.schemas.mission import ProgressPoint


class PaceStatus(str, Enum):
    """Pace status relative to goal deadline"""
    ON_TRACK = "on_track"
    AHEAD = "ahead"
    BEHIND = "behind"


class SuggestionType(str, Enum):
    """Type of coaching suggestion"""
    VOLUME = "volume"
    PLATEAU = "plateau"
    FREQUENCY = "frequency"
    SLOWDOWN = "slowdown"
    MOTIVATION = "motivation"


class SuggestionPriority(str, Enum):
    """Priority level for suggestions"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class GoalProgressReport(BaseModel):
    """Progress report for a single active goal"""
    goal_id: str
    exercise_name: str
    exercise_id: str
    target_weight: float
    target_reps: int
    weight_unit: str
    deadline: str
    starting_e1rm: Optional[float] = None
    current_e1rm: Optional[float] = None
    progress_percent: float
    required_weekly_gain: Optional[float] = None
    actual_weekly_gain: Optional[float] = None
    status: PaceStatus = PaceStatus.ON_TRACK
    projected_completion_date: Optional[str] = None
    weeks_remaining: float = 0
    actual_points: List[ProgressPoint] = []
    projected_points: List[ProgressPoint] = []


class CoachingSuggestion(BaseModel):
    """Actionable coaching suggestion"""
    type: SuggestionType
    priority: SuggestionPriority
    title: str
    description: str
    exercise_name: Optional[str] = None


class WeeklyProgressReportResponse(BaseModel):
    """Full weekly progress report with goal tracking and suggestions"""
    week_start: str
    week_end: str
    total_workouts: int
    total_sets: int
    total_volume: float
    volume_change_percent: Optional[float] = None
    prs_achieved: List[PRResponse]
    goal_reports: List[GoalProgressReport]
    suggestions: List[CoachingSuggestion]
    has_sufficient_data: bool = False
