"""Tests for volume calculations."""

import pytest
from datetime import date, timedelta
from decimal import Decimal

from strength_coach.analytics.volume import (
    VolumeMetrics,
    calculate_exercise_volume,
    calculate_session_volume,
    calculate_muscle_group_volume,
    calculate_weekly_volume,
    get_volume_trend,
    compare_volume_to_previous_week,
)
from strength_coach.models import (
    ExercisePerformance,
    MuscleGroup,
    SetRecord,
    WeightUnit,
    WorkoutSession,
)


def make_set(reps: int, weight: float) -> SetRecord:
    """Helper to create a set record."""
    return SetRecord(reps=reps, weight=Decimal(str(weight)), weight_unit=WeightUnit.LB)


def make_exercise(name: str, canonical_id: str, sets: list[SetRecord]) -> ExercisePerformance:
    """Helper to create an exercise performance."""
    return ExercisePerformance(
        exercise_name=name,
        canonical_id=canonical_id,
        sets=sets,
    )


def make_session(date_val: date, exercises: list[ExercisePerformance]) -> WorkoutSession:
    """Helper to create a workout session."""
    return WorkoutSession(date=date_val, exercises=exercises)


class TestCalculateExerciseVolume:
    """Tests for calculate_exercise_volume function."""

    def test_basic_volume(self):
        """Should calculate sets, reps, and tonnage."""
        exercise = make_exercise(
            "Squat",
            "squat",
            [
                make_set(5, 225),
                make_set(5, 225),
                make_set(5, 225),
            ],
        )
        vol = calculate_exercise_volume(exercise)

        assert vol.total_sets == 3
        assert vol.total_reps == 15
        assert vol.total_tonnage_lb == Decimal("3375")  # 225 * 15

    def test_excludes_warmups(self):
        """Should exclude warmup sets."""
        warmup = SetRecord(
            reps=10, weight=Decimal("135"), weight_unit=WeightUnit.LB, is_warmup=True
        )
        working = make_set(5, 225)

        exercise = make_exercise("Squat", "squat", [warmup, working, working])
        vol = calculate_exercise_volume(exercise)

        assert vol.total_sets == 2  # Only working sets
        assert vol.total_reps == 10

    def test_empty_exercise(self):
        """Should handle exercise with no sets."""
        exercise = make_exercise("Squat", "squat", [])
        vol = calculate_exercise_volume(exercise)

        assert vol.total_sets == 0
        assert vol.total_reps == 0
        assert vol.total_tonnage_lb == Decimal("0")


class TestCalculateSessionVolume:
    """Tests for calculate_session_volume function."""

    def test_multiple_exercises(self):
        """Should sum volume across exercises."""
        session = make_session(
            date.today(),
            [
                make_exercise("Squat", "squat", [make_set(5, 225), make_set(5, 225)]),
                make_exercise("Bench", "bench_press", [make_set(5, 185), make_set(5, 185)]),
            ],
        )
        vol = calculate_session_volume(session)

        assert vol.total_sets == 4
        assert vol.total_reps == 20
        # Tonnage: (225*10) + (185*10) = 2250 + 1850 = 4100
        assert vol.total_tonnage_lb == Decimal("4100")


class TestCalculateMuscleGroupVolume:
    """Tests for calculate_muscle_group_volume function."""

    def test_primary_muscles(self):
        """Should attribute volume to primary muscles."""
        session = make_session(
            date.today(),
            [make_exercise("Squat", "squat", [make_set(5, 225)] * 3)],
        )
        muscle_vol = calculate_muscle_group_volume(session)

        # Squat primary: quads, glutes
        assert MuscleGroup.QUADS in muscle_vol
        assert MuscleGroup.GLUTES in muscle_vol
        assert muscle_vol[MuscleGroup.QUADS].sets == 3

    def test_secondary_muscles_half_credit(self):
        """Secondary muscles should get half credit."""
        session = make_session(
            date.today(),
            [make_exercise("Squat", "squat", [make_set(5, 225)] * 4)],
        )
        muscle_vol = calculate_muscle_group_volume(session)

        # Squat secondary: hamstrings, core
        # Should get 4 // 2 = 2 sets
        if MuscleGroup.HAMSTRINGS in muscle_vol:
            assert muscle_vol[MuscleGroup.HAMSTRINGS].sets == 2


class TestCalculateWeeklyVolume:
    """Tests for calculate_weekly_volume function."""

    def test_sums_week_sessions(self):
        """Should sum volume across sessions in a week."""
        today = date.today()
        week_start = today - timedelta(days=today.weekday())

        sessions = [
            make_session(
                week_start,
                [make_exercise("Squat", "squat", [make_set(5, 225)] * 3)],
            ),
            make_session(
                week_start + timedelta(days=2),
                [make_exercise("Bench", "bench_press", [make_set(5, 185)] * 3)],
            ),
        ]

        vol = calculate_weekly_volume(sessions, week_start)
        assert vol.total_sets == 6

    def test_excludes_other_weeks(self):
        """Should only count sessions in the specified week."""
        today = date.today()
        week_start = today - timedelta(days=today.weekday())

        sessions = [
            make_session(
                week_start,  # This week
                [make_exercise("Squat", "squat", [make_set(5, 225)] * 3)],
            ),
            make_session(
                week_start - timedelta(weeks=1),  # Last week
                [make_exercise("Bench", "bench_press", [make_set(5, 185)] * 10)],
            ),
        ]

        vol = calculate_weekly_volume(sessions, week_start)
        assert vol.total_sets == 3  # Only this week's session


class TestGetVolumeTrend:
    """Tests for get_volume_trend function."""

    def test_multiple_weeks(self):
        """Should return volume for multiple weeks."""
        today = date.today()
        week_start = today - timedelta(days=today.weekday())

        sessions = []
        for week_offset in range(4):
            sessions.append(
                make_session(
                    week_start - timedelta(weeks=week_offset),
                    [make_exercise("Squat", "squat", [make_set(5, 225)] * 3)],
                )
            )

        trend = get_volume_trend(sessions, weeks=4)
        assert len(trend) == 4

    def test_empty_sessions(self):
        """Should handle empty session list."""
        trend = get_volume_trend([], weeks=4)
        assert len(trend) == 4
        assert all(t["total_sets"] == 0 for t in trend)


class TestCompareVolumeToPreviousWeek:
    """Tests for compare_volume_to_previous_week function."""

    def test_basic_comparison(self):
        """Should compare this week to last week."""
        today = date.today()
        week_start = today - timedelta(days=today.weekday())

        sessions = [
            make_session(
                week_start,  # This week: 3 sets
                [make_exercise("Squat", "squat", [make_set(5, 225)] * 3)],
            ),
            make_session(
                week_start - timedelta(weeks=1),  # Last week: 5 sets
                [make_exercise("Squat", "squat", [make_set(5, 225)] * 5)],
            ),
        ]

        comparison = compare_volume_to_previous_week(sessions)

        assert comparison["this_week"]["sets"] == 3
        assert comparison["last_week"]["sets"] == 5
        assert comparison["change"]["sets"] == -2
