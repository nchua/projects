"""Intensity and rep range distribution analysis."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from ..models import ExercisePerformance, WorkoutSession


@dataclass
class RepRangeBucket:
    """A bucket for categorizing rep ranges."""

    name: str
    min_reps: int
    max_reps: int
    training_effect: str  # strength, hypertrophy, endurance


# Standard rep range buckets
REP_RANGE_BUCKETS = [
    RepRangeBucket("Heavy (1-3)", 1, 3, "strength/power"),
    RepRangeBucket("Strength (4-6)", 4, 6, "strength"),
    RepRangeBucket("Hypertrophy (7-12)", 7, 12, "hypertrophy"),
    RepRangeBucket("Endurance (13+)", 13, 100, "muscular endurance"),
]


def get_rep_range_bucket(reps: int) -> RepRangeBucket:
    """Get the bucket for a given rep count."""
    for bucket in REP_RANGE_BUCKETS:
        if bucket.min_reps <= reps <= bucket.max_reps:
            return bucket
    return REP_RANGE_BUCKETS[-1]  # Default to endurance


@dataclass
class IntensityDistribution:
    """Distribution of sets across rep ranges."""

    heavy_sets: int  # 1-3 reps
    strength_sets: int  # 4-6 reps
    hypertrophy_sets: int  # 7-12 reps
    endurance_sets: int  # 13+ reps
    total_sets: int

    @property
    def heavy_pct(self) -> float:
        return self.heavy_sets / self.total_sets * 100 if self.total_sets else 0

    @property
    def strength_pct(self) -> float:
        return self.strength_sets / self.total_sets * 100 if self.total_sets else 0

    @property
    def hypertrophy_pct(self) -> float:
        return self.hypertrophy_sets / self.total_sets * 100 if self.total_sets else 0

    @property
    def endurance_pct(self) -> float:
        return self.endurance_sets / self.total_sets * 100 if self.total_sets else 0

    def to_dict(self) -> dict:
        return {
            "heavy": {"sets": self.heavy_sets, "pct": round(self.heavy_pct, 1)},
            "strength": {"sets": self.strength_sets, "pct": round(self.strength_pct, 1)},
            "hypertrophy": {"sets": self.hypertrophy_sets, "pct": round(self.hypertrophy_pct, 1)},
            "endurance": {"sets": self.endurance_sets, "pct": round(self.endurance_pct, 1)},
            "total_sets": self.total_sets,
        }


def calculate_exercise_intensity(performance: ExercisePerformance) -> IntensityDistribution:
    """Calculate intensity distribution for a single exercise."""
    counts = defaultdict(int)

    for set_record in performance.working_sets:
        bucket = get_rep_range_bucket(set_record.reps)
        if bucket.min_reps <= 3:
            counts["heavy"] += 1
        elif bucket.min_reps <= 6:
            counts["strength"] += 1
        elif bucket.min_reps <= 12:
            counts["hypertrophy"] += 1
        else:
            counts["endurance"] += 1

    total = sum(counts.values())

    return IntensityDistribution(
        heavy_sets=counts["heavy"],
        strength_sets=counts["strength"],
        hypertrophy_sets=counts["hypertrophy"],
        endurance_sets=counts["endurance"],
        total_sets=total,
    )


def calculate_session_intensity(session: WorkoutSession) -> IntensityDistribution:
    """Calculate intensity distribution for a full session."""
    total = IntensityDistribution(0, 0, 0, 0, 0)

    for exercise in session.exercises:
        ex_intensity = calculate_exercise_intensity(exercise)
        total = IntensityDistribution(
            heavy_sets=total.heavy_sets + ex_intensity.heavy_sets,
            strength_sets=total.strength_sets + ex_intensity.strength_sets,
            hypertrophy_sets=total.hypertrophy_sets + ex_intensity.hypertrophy_sets,
            endurance_sets=total.endurance_sets + ex_intensity.endurance_sets,
            total_sets=total.total_sets + ex_intensity.total_sets,
        )

    return total


def calculate_weekly_intensity(
    sessions: list[WorkoutSession],
    week_start: date,
) -> IntensityDistribution:
    """Calculate intensity distribution for a week."""
    week_end = week_start + timedelta(days=6)

    week_sessions = [
        s for s in sessions if week_start <= s.date <= week_end
    ]

    total = IntensityDistribution(0, 0, 0, 0, 0)

    for session in week_sessions:
        session_intensity = calculate_session_intensity(session)
        total = IntensityDistribution(
            heavy_sets=total.heavy_sets + session_intensity.heavy_sets,
            strength_sets=total.strength_sets + session_intensity.strength_sets,
            hypertrophy_sets=total.hypertrophy_sets + session_intensity.hypertrophy_sets,
            endurance_sets=total.endurance_sets + session_intensity.endurance_sets,
            total_sets=total.total_sets + session_intensity.total_sets,
        )

    return total


def analyze_intensity_by_exercise(
    sessions: list[WorkoutSession],
    exercise_id: str,
    weeks: int = 8,
) -> list[dict]:
    """Analyze rep range usage for a specific exercise over time."""
    today = date.today()
    results: list[dict] = []

    for week_offset in range(weeks - 1, -1, -1):
        week_start = today - timedelta(weeks=week_offset)
        week_start = week_start - timedelta(days=week_start.weekday())
        week_end = week_start + timedelta(days=6)

        week_sessions = [
            s for s in sessions if week_start <= s.date <= week_end
        ]

        counts = defaultdict(int)
        for session in week_sessions:
            for exercise in session.exercises:
                if (exercise.canonical_id or exercise.exercise_name.lower()) == exercise_id:
                    for set_record in exercise.working_sets:
                        bucket = get_rep_range_bucket(set_record.reps)
                        counts[bucket.name] += 1

        results.append(
            {
                "week_start": week_start.isoformat(),
                "distribution": dict(counts),
                "total_sets": sum(counts.values()),
            }
        )

    return results


def get_average_reps_per_set(session: WorkoutSession) -> float:
    """Calculate average reps per working set in a session."""
    total_reps = 0
    total_sets = 0

    for exercise in session.exercises:
        for set_record in exercise.working_sets:
            total_reps += set_record.reps
            total_sets += 1

    return total_reps / total_sets if total_sets else 0


def get_intensity_recommendation(
    current: IntensityDistribution,
    goal: str,
) -> str:
    """
    Get a recommendation based on current intensity distribution and goal.

    Args:
        current: Current intensity distribution
        goal: Training goal (strength, hypertrophy, general)

    Returns:
        Text recommendation
    """
    if goal == "strength":
        if current.heavy_pct + current.strength_pct < 50:
            return "Consider increasing sets in the 1-6 rep range for strength focus."
        return "Good intensity distribution for strength goals."

    elif goal == "hypertrophy":
        if current.hypertrophy_pct < 40:
            return "Consider increasing sets in the 7-12 rep range for hypertrophy."
        return "Good intensity distribution for hypertrophy goals."

    else:  # general
        if current.hypertrophy_pct < 30:
            return "Consider adding more moderate rep range work (7-12 reps)."
        if current.heavy_pct + current.strength_pct < 20:
            return "Consider adding some heavier work (1-6 reps) for strength development."
        return "Well-balanced intensity distribution."
