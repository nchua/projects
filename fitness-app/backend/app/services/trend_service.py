"""
Trend math for the Gate engine (ARISE v2 spec §6.1, v3 §10).

Owns the weekly-best e1RM series plus the two extensions the trend endpoint
never had: ``weekly_slope`` (least-squares over the last FIT_WINDOW_WEEKS
weekly points, lb/week) and ``projected_e1rm(days)``. Gate spawning
(gate_service) is the primary consumer; the /analytics trend endpoint keeps
its own richer payload (data points, include_sets) untouched.

v3 (§10.2): the single ``SLOPE_WINDOW_WEEKS`` was split into the minimum
number of weekly points needed to fit (``MIN_WEEKLY_POINTS = 4``) and the fit
window (``FIT_WINDOW_WEEKS = 6``), and weeks bucket on ``local_date`` (§12
0b) so a Saturday squat and a Sunday alias land in the same week honestly.
"""
from datetime import date, timedelta
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.workout import Set, WorkoutExercise, WorkoutSession
from app.services.training_load_service import local_day

# Spec §10.2: a lift needs at least MIN_WEEKLY_POINTS weeks with data before
# it can project (else no Gate); the slope is fit over the last
# FIT_WINDOW_WEEKS weekly-best points.
MIN_WEEKLY_POINTS = 4
FIT_WINDOW_WEEKS = 6


def weekly_best_e1rm_series(
    db: Session,
    user_id: str,
    exercise_ids: List[str],
    since: Optional[date] = None,
) -> List[Tuple[date, float]]:
    """Weekly best e1RM across a family's exercise ids.

    Weeks are keyed by their Monday (of the session's local day). Returns
    (week_start, best_e1rm) sorted ascending; weeks without training simply
    don't appear. Warm-up sets never count. ``since`` drops sets whose local
    day precedes it (the campaign-best baseline, §10.1).
    """
    rows = (
        db.query(WorkoutSession.local_date, WorkoutSession.date, Set.e1rm)
        .join(WorkoutExercise, WorkoutExercise.session_id == WorkoutSession.id)
        .join(Set, Set.workout_exercise_id == WorkoutExercise.id)
        .filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.deleted_at.is_(None),
            WorkoutExercise.exercise_id.in_(exercise_ids),
            Set.e1rm.isnot(None),
            Set.e1rm > 0,
            Set.is_warmup.is_(False),
        )
        .all()
    )
    weekly_best: dict = {}
    for stamped_day, instant, e1rm in rows:
        day = local_day(stamped_day, instant)
        if day is None or (since is not None and day < since):
            continue
        week_start = day - timedelta(days=day.weekday())
        if week_start not in weekly_best or e1rm > weekly_best[week_start]:
            weekly_best[week_start] = e1rm
    return sorted(weekly_best.items())


def weekly_slope(series: List[Tuple[date, float]]) -> Optional[float]:
    """Least-squares slope (lb/week) over the last FIT_WINDOW_WEEKS points.

    Requires at least MIN_WEEKLY_POINTS weeks with data (spec §10.2) —
    returns None otherwise. The x-axis is real week offsets (so a gap week
    widens the interval rather than being ignored).
    """
    if len(series) < MIN_WEEKLY_POINTS:
        return None
    window = series[-FIT_WINDOW_WEEKS:]
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
