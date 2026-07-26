"""
Shared workout statistics calculations used by the XP service and day-stat helpers.
"""
from typing import Any, Dict, Optional

from app.models.workout import WorkoutSession

# Compound exercises for stat aggregation (lowercase for matching)
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
        # Cardio (all None for strength sessions)
        **cardio_display_fields(workout),
    }


# Imperial is the app's display convention (bodyweight is logged in lb, sets in
# lb), so stored SI values are converted back to mi/ft for the client.
_METERS_PER_MILE = 1609.344
_METERS_PER_FOOT = 0.3048


def format_pace(seconds_per_mile: Optional[float]) -> Optional[str]:
    """Render seconds-per-mile as the mm'ss" string runners expect."""
    if not seconds_per_mile or seconds_per_mile <= 0:
        return None
    total = int(round(seconds_per_mile))
    return f"{total // 60}'{total % 60:02d}\""


def cardio_display_fields(workout) -> dict:
    """Client-ready cardio metrics for a session.

    Returns imperial display values alongside the raw SI numbers so clients can
    render without unit math, and analytics can still work in SI. Every key is
    present (None when absent) so iOS decoding stays uniform across session
    types.
    """
    distance_m = workout.distance_meters
    speed_mps = workout.avg_speed_mps
    elevation_m = workout.elevation_gain_meters

    pace_seconds_per_mile = (
        _METERS_PER_MILE / speed_mps if speed_mps and speed_mps > 0 else None
    )

    return {
        "distance_meters": distance_m,
        "distance_miles": round(distance_m / _METERS_PER_MILE, 2) if distance_m else None,
        "elevation_gain_meters": elevation_m,
        "elevation_gain_feet": (
            round(elevation_m / _METERS_PER_FOOT) if elevation_m is not None else None
        ),
        "avg_speed_mps": speed_mps,
        "avg_pace_seconds_per_mile": (
            round(pace_seconds_per_mile, 1) if pace_seconds_per_mile else None
        ),
        "avg_pace_display": format_pace(pace_seconds_per_mile),
        "avg_cadence_spm": workout.avg_cadence_spm,
        "avg_power_watts": workout.avg_power_watts,
        "active_calories": workout.active_calories,
        "total_calories": workout.total_calories,
    }
