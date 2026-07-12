"""
Exertion analytics endpoints (ARISE v2 spec §7.2) — the D4a surfaces.

Mounted under the /analytics prefix alongside the main analytics router:
- GET /analytics/exertion/weekly — unified-strain + volume + zone time per
  ISO week (backs the Power › Exertion small multiples).
- GET /analytics/exercise/{id}/cardiac-cost — ΔHR per matched set, the
  conditioning headline metric (falling ΔHR at the same load = engine built).
"""
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.exertion import compute_arise_strain
from app.models.exercise import Exercise
from app.models.user import User
from app.models.workout import HeartRateSample, Set, WorkoutExercise, WorkoutSession
from app.schemas.exertion import (
    CardiacCostPoint,
    CardiacCostResponse,
    ExertionWeekPoint,
    MatchedSet,
)
from app.services.pr_detection import _weight_bucket, get_canonical_exercise_ids

router = APIRouter()

ZONE_KEYS = ("z1", "z2", "z3", "z4", "z5")

# ΔHR measurement window (spec §7.2-2): peak HR inside the set plus a short
# tail, against the median bpm in the minute before the set started.
PEAK_TAIL_SECONDS = 30
BASELINE_WINDOW_SECONDS = 60

# Confounders recorded but not modeled in v1 (spec §7.2-2) — surfaced so the
# UI can footnote the metric honestly.
CARDIAC_COST_CAVEATS = [
    "Rest intervals are not modeled — short rest inflates ΔHR.",
    "Set position within the session is not modeled.",
    "RPE is not modeled — harder efforts at the same load read as higher cost.",
]


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


@router.get("/exertion/weekly", response_model=List[ExertionWeekPoint])
async def get_exertion_weekly(
    weeks: int = Query(8, ge=1, le=52),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Per-ISO-week exertion summary over the trailing ``weeks`` weeks
    (including the current week). Weeks without training still appear so
    charts keep a continuous axis.
    """
    today = date.today()
    current_monday = _week_start(today)
    first_monday = current_monday - timedelta(weeks=weeks - 1)

    workouts = (
        db.query(WorkoutSession)
        .options(
            joinedload(WorkoutSession.workout_exercises).joinedload(WorkoutExercise.sets)
        )
        .filter(
            WorkoutSession.user_id == current_user.id,
            WorkoutSession.deleted_at.is_(None),
            WorkoutSession.date >= datetime.combine(first_monday, datetime.min.time()),
        )
        .all()
    )

    buckets: Dict[date, Dict] = {
        first_monday + timedelta(weeks=i): {
            "strains": [], "count": 0, "volume": 0.0,
            "zones": {key: 0 for key in ZONE_KEYS},
        }
        for i in range(weeks)
    }

    for workout in workouts:
        day = workout.date.date() if hasattr(workout.date, "date") else workout.date
        monday = _week_start(day)
        bucket = buckets.get(monday)
        if bucket is None:
            continue
        bucket["count"] += 1

        arise = compute_arise_strain(
            workout.strain, workout.hr_zone_seconds, workout.hr_source
        )
        if arise is not None:
            bucket["strains"].append(arise["value"])

        for we in workout.workout_exercises:
            for s in we.sets:
                if s.weight and s.reps:
                    bucket["volume"] += s.weight * s.reps

        for zone, seconds in (workout.hr_zone_seconds or {}).items():
            key = str(zone).lower()
            if key in bucket["zones"] and isinstance(seconds, (int, float)):
                bucket["zones"][key] += int(seconds)

    return [
        ExertionWeekPoint(
            week_start=monday.isoformat(),
            strain_total=round(sum(b["strains"]), 1) if b["strains"] else None,
            strain_avg=round(sum(b["strains"]) / len(b["strains"]), 1) if b["strains"] else None,
            workout_count=b["count"],
            volume_lb=round(b["volume"], 1),
            zone_seconds={k: v for k, v in b["zones"].items() if v > 0},
        )
        for monday, b in sorted(buckets.items())
    ]


def _delta_hr_for_set(
    s: Set,
    session_samples: List[Tuple[datetime, int]],
    session_avg_hr: Optional[int],
) -> Optional[float]:
    """ΔHR for one set (spec §7.2-2).

    Primary: peak bpm in [start_time, end_time + 30 s] minus the median bpm
    in the 60 s before start_time (needs raw samples + set timing).
    Fallback: set.peak_heart_rate − session avg HR.
    """
    if s.start_time and s.end_time and session_samples:
        window_end = s.end_time + timedelta(seconds=PEAK_TAIL_SECONDS)
        baseline_start = s.start_time - timedelta(seconds=BASELINE_WINDOW_SECONDS)

        in_set = [bpm for ts, bpm in session_samples if s.start_time <= ts <= window_end]
        baseline = [bpm for ts, bpm in session_samples if baseline_start <= ts < s.start_time]
        if in_set and baseline:
            return float(max(in_set) - statistics.median(baseline))

    if s.peak_heart_rate is not None and session_avg_hr:
        return float(s.peak_heart_rate - session_avg_hr)
    return None


def compute_cardiac_cost(
    db: Session, user_id: str, exercise_id: str, weeks: int = 12
) -> CardiacCostResponse:
    """ΔHR-per-matched-set trend for an exercise (sync, reusable).

    Extracted from the endpoint so the achievement engine ("Engine Built":
    cardiac cost −15% on any lift) can evaluate it without HTTP.
    """
    exercise_ids = get_canonical_exercise_ids(db, exercise_id)
    cutoff = datetime.combine(date.today() - timedelta(weeks=weeks), datetime.min.time())

    rows = (
        db.query(Set, WorkoutSession)
        .join(WorkoutExercise, Set.workout_exercise_id == WorkoutExercise.id)
        .join(WorkoutSession, WorkoutExercise.session_id == WorkoutSession.id)
        .filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.deleted_at.is_(None),
            WorkoutSession.date >= cutoff,
            WorkoutExercise.exercise_id.in_(exercise_ids),
            Set.weight.isnot(None),
            Set.reps.isnot(None),
        )
        .all()
    )

    empty = CardiacCostResponse(
        exercise_id=exercise_id,
        matched_set=None,
        points=[],
        percent_change=None,
        trend_direction="insufficient_data",
        caveats=CARDIAC_COST_CAVEATS,
    )
    if not rows:
        return empty

    # Load raw HR samples once per session (only sessions that appear here).
    session_ids = {workout.id for _, workout in rows}
    samples_by_session: Dict[str, List[Tuple[datetime, int]]] = defaultdict(list)
    if session_ids:
        sample_rows = (
            db.query(HeartRateSample.session_id, HeartRateSample.timestamp, HeartRateSample.bpm)
            .filter(HeartRateSample.session_id.in_(session_ids))
            .all()
        )
        for session_id, timestamp, bpm in sample_rows:
            samples_by_session[session_id].append((timestamp, bpm))

    # ΔHR per set, grouped by (weight bucket, reps) — same bucketing PR
    # detection uses, so "matched set" means the same thing everywhere.
    groups: Dict[Tuple[float, int], List[Tuple[date, float]]] = defaultdict(list)
    for s, workout in rows:
        delta = _delta_hr_for_set(
            s, samples_by_session.get(workout.id, []), workout.avg_heart_rate
        )
        if delta is None:
            continue
        day = workout.date.date() if hasattr(workout.date, "date") else workout.date
        groups[(_weight_bucket(s.weight), s.reps)].append((day, delta))

    # Largest group with >=2 distinct weeks of data (spec §7.2-2).
    best_key = None
    best_size = 0
    for key, entries in groups.items():
        distinct_weeks = {_week_start(day) for day, _ in entries}
        if len(distinct_weeks) >= 2 and len(entries) > best_size:
            best_key = key
            best_size = len(entries)

    if best_key is None:
        return empty

    weekly: Dict[date, List[float]] = defaultdict(list)
    for day, delta in groups[best_key]:
        weekly[_week_start(day)].append(delta)

    points = [
        CardiacCostPoint(
            week_start=monday.isoformat(),
            delta_hr_median=round(statistics.median(deltas), 1),
            n_sets=len(deltas),
        )
        for monday, deltas in sorted(weekly.items())
    ]

    first, last = points[0].delta_hr_median, points[-1].delta_hr_median
    percent_change = round((last - first) / first * 100, 1) if first > 0 else None

    # Falling ΔHR = conditioning gain → "improving" (TrendDirection vocab).
    if percent_change is None:
        trend = "insufficient_data"
    elif percent_change <= -2:
        trend = "improving"
    elif percent_change >= 2:
        trend = "regressing"
    else:
        trend = "stable"

    return CardiacCostResponse(
        exercise_id=exercise_id,
        matched_set=MatchedSet(weight=best_key[0], reps=best_key[1]),
        points=points,
        percent_change=percent_change,
        trend_direction=trend,
        caveats=CARDIAC_COST_CAVEATS,
    )


@router.get("/exercise/{exercise_id}/cardiac-cost", response_model=CardiacCostResponse)
async def get_cardiac_cost(
    exercise_id: str,
    weeks: int = Query(12, ge=2, le=52),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    ΔHR per matched set for an exercise (canonical alias group), normalized
    by (weight bucket, reps) — the largest group with ≥2 weeks of data.
    Falling ΔHR at the same load over weeks = conditioning gain.
    """
    exercise = db.query(Exercise).filter(Exercise.id == exercise_id).first()
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    return compute_cardiac_cost(db, current_user.id, exercise_id, weeks)
