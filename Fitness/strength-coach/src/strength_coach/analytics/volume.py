"""Volume and tonnage calculations."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from ..models import (
    ExercisePerformance,
    MuscleGroup,
    WorkoutSession,
    get_exercise,
    get_muscles_for_exercise,
)


@dataclass
class VolumeMetrics:
    """Volume metrics for a period."""

    total_sets: int
    total_reps: int
    total_tonnage_lb: Decimal
    exercises_performed: list[str]


@dataclass
class MuscleVolumeMetrics:
    """Volume metrics broken down by muscle group."""

    muscle_group: MuscleGroup
    sets: int
    tonnage_lb: Decimal
    exercises: list[str]


def calculate_exercise_volume(performance: ExercisePerformance) -> VolumeMetrics:
    """Calculate volume metrics for a single exercise performance."""
    working_sets = performance.working_sets

    return VolumeMetrics(
        total_sets=len(working_sets),
        total_reps=sum(s.reps for s in working_sets),
        total_tonnage_lb=sum(s.weight_lb * s.reps for s in working_sets),
        exercises_performed=[performance.canonical_id or performance.exercise_name],
    )


def calculate_session_volume(session: WorkoutSession) -> VolumeMetrics:
    """Calculate total volume metrics for a workout session."""
    total_sets = 0
    total_reps = 0
    total_tonnage = Decimal("0")
    exercises: list[str] = []

    for exercise in session.exercises:
        ex_vol = calculate_exercise_volume(exercise)
        total_sets += ex_vol.total_sets
        total_reps += ex_vol.total_reps
        total_tonnage += ex_vol.total_tonnage_lb
        exercises.extend(ex_vol.exercises_performed)

    return VolumeMetrics(
        total_sets=total_sets,
        total_reps=total_reps,
        total_tonnage_lb=total_tonnage,
        exercises_performed=exercises,
    )


def calculate_muscle_group_volume(
    session: WorkoutSession,
) -> dict[MuscleGroup, MuscleVolumeMetrics]:
    """
    Calculate volume broken down by muscle group.

    Primary muscles get full credit, secondary muscles get half credit.
    """
    muscle_data: dict[MuscleGroup, dict] = defaultdict(
        lambda: {"sets": 0, "tonnage": Decimal("0"), "exercises": set()}
    )

    for exercise in session.exercises:
        exercise_id = exercise.canonical_id or exercise.exercise_name
        primary, secondary = get_muscles_for_exercise(exercise_id)

        ex_vol = calculate_exercise_volume(exercise)

        # Primary muscles get full credit
        for muscle in primary:
            muscle_data[muscle]["sets"] += ex_vol.total_sets
            muscle_data[muscle]["tonnage"] += ex_vol.total_tonnage_lb
            muscle_data[muscle]["exercises"].add(exercise_id)

        # Secondary muscles get half credit (rounded)
        for muscle in secondary:
            muscle_data[muscle]["sets"] += ex_vol.total_sets // 2
            muscle_data[muscle]["tonnage"] += ex_vol.total_tonnage_lb / 2
            muscle_data[muscle]["exercises"].add(exercise_id)

    return {
        muscle: MuscleVolumeMetrics(
            muscle_group=muscle,
            sets=data["sets"],
            tonnage_lb=data["tonnage"],
            exercises=list(data["exercises"]),
        )
        for muscle, data in muscle_data.items()
    }


def calculate_weekly_volume(
    sessions: list[WorkoutSession],
    week_start: date,
) -> VolumeMetrics:
    """Calculate total volume for a week starting on the given date."""
    week_end = week_start + timedelta(days=6)

    week_sessions = [
        s for s in sessions if week_start <= s.date <= week_end
    ]

    total_sets = 0
    total_reps = 0
    total_tonnage = Decimal("0")
    all_exercises: list[str] = []

    for session in week_sessions:
        vol = calculate_session_volume(session)
        total_sets += vol.total_sets
        total_reps += vol.total_reps
        total_tonnage += vol.total_tonnage_lb
        all_exercises.extend(vol.exercises_performed)

    return VolumeMetrics(
        total_sets=total_sets,
        total_reps=total_reps,
        total_tonnage_lb=total_tonnage,
        exercises_performed=list(set(all_exercises)),
    )


def calculate_weekly_muscle_volume(
    sessions: list[WorkoutSession],
    week_start: date,
) -> dict[MuscleGroup, MuscleVolumeMetrics]:
    """Calculate muscle group volume for a week."""
    week_end = week_start + timedelta(days=6)

    week_sessions = [
        s for s in sessions if week_start <= s.date <= week_end
    ]

    combined: dict[MuscleGroup, dict] = defaultdict(
        lambda: {"sets": 0, "tonnage": Decimal("0"), "exercises": set()}
    )

    for session in week_sessions:
        session_muscle_vol = calculate_muscle_group_volume(session)
        for muscle, metrics in session_muscle_vol.items():
            combined[muscle]["sets"] += metrics.sets
            combined[muscle]["tonnage"] += metrics.tonnage_lb
            combined[muscle]["exercises"].update(metrics.exercises)

    return {
        muscle: MuscleVolumeMetrics(
            muscle_group=muscle,
            sets=data["sets"],
            tonnage_lb=data["tonnage"],
            exercises=list(data["exercises"]),
        )
        for muscle, data in combined.items()
    }


def get_volume_trend(
    sessions: list[WorkoutSession],
    weeks: int = 8,
) -> list[dict]:
    """
    Get volume trend over the past N weeks.

    Returns list of weekly volume summaries.
    """
    today = date.today()
    results: list[dict] = []

    for week_offset in range(weeks - 1, -1, -1):
        week_start = today - timedelta(weeks=week_offset)
        week_start = week_start - timedelta(days=week_start.weekday())  # Monday

        vol = calculate_weekly_volume(sessions, week_start)

        results.append(
            {
                "week_start": week_start.isoformat(),
                "total_sets": vol.total_sets,
                "total_reps": vol.total_reps,
                "total_tonnage_lb": float(vol.total_tonnage_lb),
                "exercise_count": len(vol.exercises_performed),
            }
        )

    return results


def compare_volume_to_previous_week(
    sessions: list[WorkoutSession],
) -> dict:
    """Compare this week's volume to last week's."""
    today = date.today()
    this_week_start = today - timedelta(days=today.weekday())
    last_week_start = this_week_start - timedelta(weeks=1)

    this_week_vol = calculate_weekly_volume(sessions, this_week_start)
    last_week_vol = calculate_weekly_volume(sessions, last_week_start)

    def pct_change(new: Decimal, old: Decimal) -> float:
        if old == 0:
            return 0.0 if new == 0 else 100.0
        return float((new - old) / old * 100)

    return {
        "this_week": {
            "sets": this_week_vol.total_sets,
            "tonnage_lb": float(this_week_vol.total_tonnage_lb),
        },
        "last_week": {
            "sets": last_week_vol.total_sets,
            "tonnage_lb": float(last_week_vol.total_tonnage_lb),
        },
        "change": {
            "sets": this_week_vol.total_sets - last_week_vol.total_sets,
            "sets_pct": pct_change(
                Decimal(this_week_vol.total_sets), Decimal(last_week_vol.total_sets)
            ),
            "tonnage_pct": pct_change(
                this_week_vol.total_tonnage_lb, last_week_vol.total_tonnage_lb
            ),
        },
    }
