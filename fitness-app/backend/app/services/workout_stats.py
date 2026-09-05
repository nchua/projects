"""
Neutral workout statistics helpers.

Shared by the XP service, the Directive engine and the day-stat consumers.
``calculate_todays_workout_stats`` and ``user_has_wearable`` moved here from
the retired ``quest_service`` (ARISE v3 spec §11) so nothing depends on the
quest module any more. Warm-up sets (``Set.is_warmup``, §7.5) are excluded
from every set/rep/volume count.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict

from sqlalchemy.orm import Session, joinedload

from app.models.workout import WorkoutExercise, WorkoutSession

# Compound exercises for stat aggregation (lowercase for matching)
COMPOUND_EXERCISES = [
    "back squat", "squat", "front squat",
    "bench press", "flat bench", "incline bench",
    "deadlift", "conventional deadlift", "sumo deadlift", "romanian deadlift",
    "overhead press", "shoulder press", "military press",
    "barbell row", "bent over row", "pendlay row",
]


def _is_working_set(set_obj: Any) -> bool:
    """False for warm-up sets; tolerant of mocks without the attribute."""
    return not getattr(set_obj, "is_warmup", False)


def calculate_workout_stats(workout: WorkoutSession) -> Dict[str, Any]:
    """
    Calculate aggregate stats from a single workout.

    Args:
        workout: A WorkoutSession with workout_exercises and sets loaded.

    Returns:
        Dict with total_sets, total_reps, compound_sets, total_volume,
        unique_exercises, and exercise_names. Warm-up sets are excluded.
    """
    total_sets = 0
    total_reps = 0
    compound_sets = 0
    total_volume = 0
    exercise_names: list[str] = []

    for workout_exercise in workout.workout_exercises:
        exercise_name = workout_exercise.exercise.name.lower() if workout_exercise.exercise else ""
        if exercise_name and exercise_name not in exercise_names:
            exercise_names.append(exercise_name)

        for set_obj in workout_exercise.sets:
            if not _is_working_set(set_obj):
                continue
            total_sets += 1
            total_reps += set_obj.reps
            total_volume += set_obj.weight * set_obj.reps

            if any(compound in exercise_name for compound in COMPOUND_EXERCISES):
                compound_sets += 1

    # Wearable HR metrics (None when no wearable data is attached to the session).
    # hr_zone_seconds is a {"z1": secs, ...} map; expose minutes per zone for
    # day-stat consumers, plus total elevated-zone minutes (z2 and above).
    zone_seconds = workout.hr_zone_seconds or {}
    zone_minutes = {z: int(secs) // 60 for z, secs in zone_seconds.items()}
    elevated_zone_minutes = sum(
        m for z, m in zone_minutes.items() if z in ("z2", "z3", "z4", "z5")
    )

    return {
        "total_sets": total_sets,
        "total_reps": total_reps,
        "compound_sets": compound_sets,
        "total_volume": int(total_volume),
        "unique_exercises": len(exercise_names),
        "exercise_names": exercise_names,
        # Heart-rate / exertion
        "avg_heart_rate": workout.avg_heart_rate,
        "peak_heart_rate": workout.peak_heart_rate,
        "strain": workout.strain,
        "zone_minutes": zone_minutes,
        "elevated_zone_minutes": elevated_zone_minutes,
    }


def calculate_todays_workout_stats(db: Session, user_id: str, target_date: date) -> Dict[str, Any]:
    """
    Calculate aggregate stats from workouts for a specific date.

    Only workouts matching the exact target_date are included. Earlier workouts
    from the week do NOT count. Warm-up sets are excluded.

    Args:
        db: Database session
        user_id: User ID
        target_date: The specific date to calculate stats for

    Returns:
        Dict with total_reps, compound_sets, total_volume, and workout_count
    """
    # Get workouts for the target date with their exercises and sets
    day_start = datetime.combine(target_date, datetime.min.time())
    day_end = datetime.combine(target_date + timedelta(days=1), datetime.min.time())

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
                if not _is_working_set(set_obj):
                    continue
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
    # Local import: whoop_service imports models this module also touches, so
    # keep the dependency one-directional at import time.
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
