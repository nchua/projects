"""
Analytics Pydantic schemas for request/response validation
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date as date_type
from enum import Enum


class TrendDirection(str, Enum):
    """Trend direction for exercise progress"""
    IMPROVING = "improving"
    STABLE = "stable"
    REGRESSING = "regressing"
    INSUFFICIENT_DATA = "insufficient_data"


class TimeRange(str, Enum):
    """Time range options for analytics"""
    FOUR_WEEKS = "4w"
    TWELVE_WEEKS = "12w"
    ONE_YEAR = "1y"
    ALL_TIME = "all"


class SetDetail(BaseModel):
    """Set info for chart data point drill-down"""
    weight: float
    reps: int
    e1rm: float


class DataPoint(BaseModel):
    """A single data point for time series"""
    date: str
    value: float
    sets: Optional[List["SetDetail"]] = None  # Populated when include_sets=True


class TrendResponse(BaseModel):
    """Response for exercise trend data"""
    exercise_id: str
    exercise_name: str
    time_range: str
    data_points: List[DataPoint]
    weekly_best_e1rm: List[DataPoint]
    rolling_average_4w: Optional[float] = None
    current_e1rm: Optional[float] = None
    trend_direction: TrendDirection = TrendDirection.INSUFFICIENT_DATA
    percent_change: Optional[float] = None
    total_workouts: int = 0


class SetHistoryItem(BaseModel):
    """A set in the history"""
    date: str
    workout_id: str
    weight: float
    reps: int
    rpe: Optional[int] = None
    rir: Optional[int] = None
    e1rm: float
    set_number: int


class SessionGroup(BaseModel):
    """Sets grouped by workout session"""
    workout_id: str
    date: str
    sets: List[SetHistoryItem]


class ExerciseHistoryResponse(BaseModel):
    """Response for complete exercise set history"""
    exercise_id: str
    exercise_name: str
    sessions: List[SessionGroup]
    total_sets: int = 0
    best_e1rm: Optional[float] = None
    best_volume_session: Optional[str] = None


class StrengthClassification(str, Enum):
    """Strength level classification"""
    BEGINNER = "beginner"
    NOVICE = "novice"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    ELITE = "elite"


class ExercisePercentile(BaseModel):
    """Percentile data for a single exercise"""
    exercise_id: str
    exercise_name: str
    current_e1rm: Optional[float] = None
    bodyweight_multiplier: Optional[float] = None
    percentile: Optional[int] = None
    classification: StrengthClassification = StrengthClassification.BEGINNER


class PercentilesResponse(BaseModel):
    """Response for strength percentiles"""
    user_bodyweight: Optional[float] = None
    user_age: Optional[int] = None
    user_sex: Optional[str] = None
    exercises: List[ExercisePercentile]


class PRType(str, Enum):
    """Type of personal record"""
    E1RM = "e1rm"
    REP_PR = "rep_pr"


class PRResponse(BaseModel):
    """Response for a personal record"""
    id: str
    exercise_id: str
    exercise_name: str
    canonical_id: Optional[str] = None
    canonical_exercise_name: Optional[str] = None
    pr_type: PRType
    value: Optional[float] = None  # For e1RM PRs
    reps: Optional[int] = None  # For rep PRs
    weight: Optional[float] = None  # For rep PRs
    achieved_at: str
    created_at: str


class PRListResponse(BaseModel):
    """Response for list of PRs"""
    prs: List[PRResponse]
    total_count: int


class InsightType(str, Enum):
    """Type of workout insight"""
    IMPROVING = "improving"
    PLATEAU = "plateau"
    REGRESSING = "regressing"
    VOLUME_HIGH = "volume_high"
    VOLUME_LOW = "volume_low"
    IMBALANCE = "imbalance"
    PR_STREAK = "pr_streak"


class InsightPriority(str, Enum):
    """Priority level for insights"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Insight(BaseModel):
    """A workout insight"""
    type: InsightType
    priority: InsightPriority
    title: str
    description: str
    exercise_id: Optional[str] = None
    exercise_name: Optional[str] = None
    data: Optional[dict] = None


class InsightsResponse(BaseModel):
    """Response for workout insights"""
    insights: List[Insight]
    generated_at: str


class WeeklyReviewResponse(BaseModel):
    """Response for weekly review summary"""
    week_start: str
    week_end: str
    total_workouts: int
    total_sets: int
    total_volume: float
    prs_achieved: List[PRResponse]
    volume_change_percent: Optional[float] = None
    fastest_improving_exercise: Optional[str] = None
    fastest_improving_percent: Optional[float] = None
    regressing_exercises: List[str]
    insights: List[Insight]
