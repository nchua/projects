"""Weekly review report generation."""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from ..models import WorkoutSession, BodyWeightEntry, UserProfile, DEFAULT_USER_PROFILE
from ..analytics import (
    calculate_weekly_volume,
    calculate_weekly_muscle_volume,
    calculate_weekly_intensity,
    get_exercise_trend,
    detect_session_prs,
    build_pr_history,
    PRRecord,
)
from ..recomp import analyze_weight_trends, detect_recomp_signal
from ..percentiles import default_provider, PercentileResult
from ..storage import StorageBackend


@dataclass
class WeeklyHighlight:
    """A notable event from the week."""

    type: str  # "pr", "volume", "consistency", "warning"
    message: str
    priority: int = 0  # Higher = more important


@dataclass
class WeeklyReviewData:
    """Compiled data for weekly review."""

    week_start: date
    week_end: date

    # Session summary
    session_count: int
    session_days: list[str]
    total_sets: int
    total_volume_lb: Decimal
    avg_session_rpe: Optional[float]

    # Exercise highlights
    exercises_performed: list[str]
    new_prs: list[PRRecord]

    # Lift progress (for tracked lifts)
    lift_progress: dict[str, dict]  # {lift_id: {current_e1rm, change_pct, trend}}

    # Volume by muscle group
    muscle_volume: dict[str, dict]  # {muscle: {sets, tonnage}}

    # Intensity distribution
    intensity: dict[str, dict]  # {bucket: {sets, pct}}

    # Body weight
    weight_data: Optional[dict] = None

    # Recomp signal
    recomp_signal: Optional[dict] = None

    # Percentiles
    percentiles: dict[str, PercentileResult] = field(default_factory=dict)

    # Highlights
    highlights: list[WeeklyHighlight] = field(default_factory=list)


def generate_weekly_review(
    storage: StorageBackend,
    week_start: Optional[date] = None,
    user_profile: Optional[UserProfile] = None,
) -> WeeklyReviewData:
    """
    Generate a comprehensive weekly review.

    Args:
        storage: Storage backend to query data from
        week_start: Start of week (defaults to current week's Monday)
        user_profile: User profile for percentile calculations

    Returns:
        WeeklyReviewData with all computed metrics
    """
    if user_profile is None:
        user_profile = DEFAULT_USER_PROFILE

    # Default to current week
    if week_start is None:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())

    week_end = week_start + timedelta(days=6)

    # Get sessions for this week
    sessions = storage.get_sessions(start_date=week_start, end_date=week_end)

    # Session summary
    session_count = len(sessions)
    session_days = [s.date.strftime("%a") for s in sessions]

    # Calculate totals
    total_sets = sum(s.total_sets for s in sessions)
    total_volume = sum(s.total_volume_lb for s in sessions)

    # Average RPE
    session_rpes = [s.session_rpe for s in sessions if s.session_rpe is not None]
    avg_rpe = sum(session_rpes) / len(session_rpes) if session_rpes else None

    # Exercises performed
    all_exercises = set()
    for session in sessions:
        for ex in session.exercises:
            all_exercises.add(ex.canonical_id or ex.exercise_name)
    exercises_performed = sorted(all_exercises)

    # PR detection
    all_prs: dict[str, dict[str, PRRecord]] = {}
    for exercise_id in exercises_performed:
        history = storage.get_exercise_history(exercise_id)
        all_prs[exercise_id] = build_pr_history(history, exercise_id)

    new_prs: list[PRRecord] = []
    for session in sessions:
        session_prs = detect_session_prs(session, all_prs)
        new_prs.extend(session_prs)
        # Update historical PRs
        for pr in session_prs:
            if pr.exercise_id not in all_prs:
                all_prs[pr.exercise_id] = {}
            all_prs[pr.exercise_id][pr.pr_type] = pr

    # Lift progress for tracked lifts
    tracked_lifts = ["squat", "bench_press", "deadlift", "overhead_press"]
    lift_progress = {}

    for lift in tracked_lifts:
        history = storage.get_exercise_history(lift)
        if history:
            trend = get_exercise_trend(history)
            lift_progress[lift] = {
                "current_e1rm": trend["current_e1rm"],
                "e1rm_4wk_ago": trend["e1rm_n_weeks_ago"],
                "change_pct": trend["e1rm_change_pct"],
                "trend": trend["trend_direction"],
            }

    # Muscle volume
    muscle_vol = calculate_weekly_muscle_volume(sessions, week_start)
    muscle_volume = {
        mg.value: {"sets": mv.sets, "tonnage_lb": float(mv.tonnage_lb)}
        for mg, mv in muscle_vol.items()
    }

    # Intensity distribution
    intensity_dist = calculate_weekly_intensity(sessions, week_start)
    intensity = intensity_dist.to_dict()

    # Body weight
    weight_entries = storage.get_bodyweight_entries(
        start_date=week_start - timedelta(weeks=4),
        end_date=week_end,
    )
    weight_data = None
    recomp_signal = None

    if weight_entries:
        weight_analysis = analyze_weight_trends(weight_entries)
        weight_data = {
            "current": float(weight_analysis.current_weight),
            "rolling_avg": float(weight_analysis.rolling_7day_avg),
            "weekly_change": float(weight_analysis.weekly_change_lb),
            "trend_4wk": weight_analysis.trend_4wk,
            "alerts": weight_analysis.alerts,
        }

        # Recomp signal (use first tracked lift trend)
        if lift_progress:
            first_lift = next(iter(lift_progress.values()))
            recomp = detect_recomp_signal(
                weight_analysis,
                {"trend_direction": first_lift["trend"], "e1rm_change_pct": first_lift["change_pct"]},
            )
            recomp_signal = {
                "is_likely": recomp.is_recomp_likely,
                "confidence": recomp.confidence,
                "explanation": recomp.explanation,
            }

    # Percentiles
    percentiles = {}
    bodyweight = (
        Decimal(str(weight_data["rolling_avg"]))
        if weight_data
        else user_profile.default_bodyweight_lb
    )

    for lift, progress in lift_progress.items():
        if progress["current_e1rm"] > 0:
            try:
                pct = default_provider.get_percentile(
                    lift,
                    progress["current_e1rm"],
                    bodyweight,
                    user_profile.sex,
                    user_profile.age,
                )
                percentiles[lift] = pct
            except ValueError:
                pass  # Unsupported lift

    # Generate highlights
    highlights: list[WeeklyHighlight] = []

    # PR highlights
    for pr in new_prs:
        if pr.pr_type == "e1rm":
            highlights.append(
                WeeklyHighlight(
                    type="pr",
                    message=f"New {pr.exercise_id} e1RM: {pr.value} lb",
                    priority=10,
                )
            )

    # Consistency highlight
    if session_count >= 3:
        highlights.append(
            WeeklyHighlight(
                type="consistency",
                message=f"Hit {session_count} sessions this week",
                priority=5,
            )
        )

    # Volume highlight
    if total_sets >= 40:
        highlights.append(
            WeeklyHighlight(
                type="volume",
                message=f"High volume week: {total_sets} total sets",
                priority=3,
            )
        )

    # Sort highlights by priority
    highlights.sort(key=lambda h: h.priority, reverse=True)

    return WeeklyReviewData(
        week_start=week_start,
        week_end=week_end,
        session_count=session_count,
        session_days=session_days,
        total_sets=total_sets,
        total_volume_lb=total_volume,
        avg_session_rpe=avg_rpe,
        exercises_performed=exercises_performed,
        new_prs=new_prs,
        lift_progress=lift_progress,
        muscle_volume=muscle_volume,
        intensity=intensity,
        weight_data=weight_data,
        recomp_signal=recomp_signal,
        percentiles=percentiles,
        highlights=highlights,
    )
