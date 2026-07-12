"""
Trend math for the Gate engine (ARISE v2 spec §6.1).

Owns the weekly-best e1RM series plus the two extensions the trend endpoint
never had: ``weekly_slope`` (least-squares over the last 6 weekly points,
lb/week) and ``projected_e1rm(days)``. Gate spawning (gate_service) is the
primary consumer; the /analytics trend endpoint keeps its own richer payload
(data points, include_sets) untouched.
"""
from datetime import date, timedelta
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.workout import Set, WorkoutExercise, WorkoutSession

# Spec §6.1: slope is fit over the last 6 weekly-best points, and a lift needs
# at least 6 weeks with data before it can project (else no Gate).
SLOPE_WINDOW_WEEKS = 6


def weekly_best_e1rm_series(
    db: Session, user_id: str, exercise_ids: List[str]
) -> List[Tuple[date, float]]:
    """Weekly best e1RM across an exercise's canonical alias group.

    Weeks are keyed by their Monday. Returns (week_start, best_e1rm) sorted
    ascending; weeks without training simply don't appear.
    """
    rows = (
        db.query(WorkoutSession.date, Set.e1rm)
        .join(WorkoutExercise, WorkoutExercise.session_id == WorkoutSession.id)
        .join(Set, Set.workout_exercise_id == WorkoutExercise.id)
        .filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.deleted_at.is_(None),
            WorkoutExercise.exercise_id.in_(exercise_ids),
            Set.e1rm.isnot(None),
            Set.e1rm > 0,
        )
        .all()
    )
    weekly_best: dict = {}
    for workout_date, e1rm in rows:
        day = workout_date.date() if hasattr(workout_date, "date") else workout_date
        week_start = day - timedelta(days=day.weekday())
        if week_start not in weekly_best or e1rm > weekly_best[week_start]:
            weekly_best[week_start] = e1rm
    return sorted(weekly_best.items())


def weekly_slope(series: List[Tuple[date, float]]) -> Optional[float]:
    """Least-squares slope (lb/week) over the last SLOPE_WINDOW_WEEKS points.

    Requires at least SLOPE_WINDOW_WEEKS weeks with data (spec §6.1) — returns
    None otherwise. The x-axis is real week offsets (so a gap week widens the
    interval rather than being ignored).
    """
    if len(series) < SLOPE_WINDOW_WEEKS:
        return None
    window = series[-SLOPE_WINDOW_WEEKS:]
    origin = window[0][0]
    xs = [(week - origin).days / 7.0 for week, _ in window]
    ys = [value for _, value in window]

    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom
    return round(slope, 3)


def projected_e1rm(current_e1rm: float, slope: float, days: int) -> float:
    """Project e1RM ``days`` out: current + slope × days/7 (spec §6.1).

    Only meaningful while the trend is improving (slope > 0) — callers gate
    on that.
    """
    return round(current_e1rm + slope * days / 7.0, 2)
