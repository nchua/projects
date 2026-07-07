"""
Quest Service - workout stat aggregation and wearable detection.

Daily-quest generation/claim was removed in ARISE v2 Phase 0; the helpers
below survive because the Phase 1 Directive system reuses them. The
quest_definitions / user_quests tables also stay until Phase 1.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict

from sqlalchemy.orm import Session, joinedload

from app.models.workout import WorkoutExercise, WorkoutSession
from app.services.workout_stats import COMPOUND_EXERCISES


def get_midnight_utc_tomorrow() -> datetime:
    """Get the next midnight UTC"""
    now = datetime.now(timezone.utc)
    tomorrow = now.date() + timedelta(days=1)
    return datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, 0, tzinfo=timezone.utc)


def get_today_utc() -> date:
    """Get today's date in UTC"""
    return datetime.now(timezone.utc).date()


def calculate_todays_workout_stats(db: Session, user_id: str, target_date: date) -> Dict[str, Any]:
    """
    Calculate aggregate stats from workouts for a specific date.

    Only workouts matching the exact target_date are included. Earlier workouts
    from the week do NOT count.

    Args:
        db: Database session
        user_id: User ID
        target_date: The specific date to calculate stats for

    Returns:
        Dict with total_reps, compound_sets, total_volume, and workout_count
    """
    # Get workouts for the target date with their exercises and sets
    from datetime import datetime as _dt
    day_start = _dt.combine(target_date, _dt.min.time())
    day_end = _dt.combine(target_date + timedelta(days=1), _dt.min.time())

    matching_workouts = db.query(WorkoutSession).options(
        joinedload(WorkoutSession.workout_exercises)
        .joinedload(WorkoutExercise.sets),
        joinedload(WorkoutSession.workout_exercises)
        .joinedload(WorkoutExercise.exercise)
    ).filter(
        WorkoutSession.user_id == user_id,
        WorkoutSession.deleted_at == None,
        WorkoutSession.date >= day_start,
        WorkoutSession.date < day_end
    ).all()

    total_reps = 0
    compound_sets = 0
    total_volume = 0
    # Wearable HR: time-in-zone sums across the day, peak HR / strain take the
    # best (max) of the day's sessions.
    elevated_zone_minutes = 0
    peak_heart_rate = 0
    strain = 0.0

    for workout in matching_workouts:
        for workout_exercise in workout.workout_exercises:
            exercise_name = workout_exercise.exercise.name.lower() if workout_exercise.exercise else ""

            for set_obj in workout_exercise.sets:
                total_reps += set_obj.reps
                total_volume += set_obj.weight * set_obj.reps

                if any(compound in exercise_name for compound in COMPOUND_EXERCISES):
                    compound_sets += 1

        zone_seconds = workout.hr_zone_seconds or {}
        elevated_zone_minutes += sum(
            int(secs) // 60 for z, secs in zone_seconds.items()
            if z in ("z2", "z3", "z4", "z5")
        )
        if workout.peak_heart_rate:
            peak_heart_rate = max(peak_heart_rate, workout.peak_heart_rate)
        if workout.strain:
            strain = max(strain, workout.strain)

    return {
        "total_reps": total_reps,
        "compound_sets": compound_sets,
        "total_volume": int(total_volume),
        "workout_count": len(matching_workouts),
        "elevated_zone_minutes": elevated_zone_minutes,
        "peak_heart_rate": peak_heart_rate,
        "strain": strain,
    }


def user_has_wearable(db: Session, user_id: str, lookback_days: int = 30) -> bool:
    """
    True if the user has a usable wearable HR source:
      - a connected WHOOP account, OR
      - any recent (non-deleted) workout carrying wearable HR (``hr_source`` set,
        e.g. from an Apple Watch HealthKit import or WHOOP sync).

    Used to gate HR-driven content so non-wearable users never get
    impossible objectives.
    """
    # Local import: whoop_service imports this module, so a top-level import
    # would create a cycle.
    from app.services import whoop_service

    if whoop_service.get_connection(db, user_id) is not None:
        return True

    # Naive UTC to match how WorkoutSession.date is stored (see whoop_service /
    # the rest of the schema) — comparing naive vs. aware breaks under SQLite.
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=lookback_days)
    recent_hr_session = (
        db.query(WorkoutSession.id)
        .filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.hr_source.isnot(None),
            WorkoutSession.date >= cutoff,
            WorkoutSession.deleted_at.is_(None),
        )
        .first()
    )
    return recent_hr_session is not None
