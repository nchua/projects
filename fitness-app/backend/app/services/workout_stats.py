"""
Shared workout statistics calculations used by quest, dungeon, and XP services.
"""
from typing import Any, Dict

from app.models.workout import WorkoutSession

# Compound exercises for quest/dungeon checking (lowercase for matching)
COMPOUND_EXERCISES = [
    "back squat", "squat", "front squat",
    "bench press", "flat bench", "incline bench",
    "deadlift", "conventional deadlift", "sumo deadlift", "romanian deadlift",
    "overhead press", "shoulder press", "military press",
    "barbell row", "bent over row", "pendlay row",
]


def calculate_workout_stats(workout: WorkoutSession) -> Dict[str, Any]:
    """
    Calculate aggregate stats from a single workout.

    Args:
        workout: A WorkoutSession with workout_exercises and sets loaded.

    Returns:
        Dict with total_sets, total_reps, compound_sets, total_volume,
        unique_exercises, and exercise_names.
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
            total_sets += 1
            total_reps += set_obj.reps
            total_volume += set_obj.weight * set_obj.reps

            if any(compound in exercise_name for compound in COMPOUND_EXERCISES):
                compound_sets += 1

    # Wearable HR metrics (None when no wearable data is attached to the session).
    # hr_zone_seconds is a {"z1": secs, ...} map; expose minutes per zone for
    # HR_ZONE_TIME quests, plus total elevated-zone minutes (z2 and above).
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
