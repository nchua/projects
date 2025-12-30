"""Tests for PR detection."""

import pytest
from datetime import date
from decimal import Decimal

from strength_coach.analytics.prs import (
    PRRecord,
    detect_set_prs,
    detect_exercise_prs,
    detect_session_prs,
    build_pr_history,
    format_pr_for_display,
)
from strength_coach.models import (
    ExercisePerformance,
    SetRecord,
    WeightUnit,
    WorkoutSession,
)


class TestDetectSetPRs:
    """Tests for detect_set_prs function."""

    def test_first_set_creates_prs(self):
        """First set for an exercise should create PRs."""
        set_record = SetRecord(
            reps=5, weight=Decimal("225"), weight_unit=WeightUnit.LB
        )
        prs = detect_set_prs(set_record, "squat", date.today(), {})

        # Should have e1RM PR and rep_pr_5, rep_pr_3, rep_pr_1
        assert len(prs) >= 3
        pr_types = {pr.pr_type for pr in prs}
        assert "e1rm" in pr_types
        assert "rep_pr_5" in pr_types

    def test_higher_weight_creates_pr(self):
        """Higher weight than historical should create PR."""
        historical = {
            "e1rm": PRRecord(
                exercise_id="squat",
                pr_type="e1rm",
                value=Decimal("300"),
                date=date.today(),
            )
        }
        set_record = SetRecord(
            reps=5, weight=Decimal("275"), weight_unit=WeightUnit.LB
        )
        # 275 x 5 = ~321 e1RM (Epley)
        prs = detect_set_prs(set_record, "squat", date.today(), historical)

        e1rm_prs = [pr for pr in prs if pr.pr_type == "e1rm"]
        assert len(e1rm_prs) == 1
        assert e1rm_prs[0].value > Decimal("300")

    def test_lower_weight_no_pr(self):
        """Lower weight than historical should not create PR."""
        historical = {
            "e1rm": PRRecord(
                exercise_id="squat",
                pr_type="e1rm",
                value=Decimal("400"),
                date=date.today(),
            ),
            "rep_pr_5": PRRecord(
                exercise_id="squat",
                pr_type="rep_pr_5",
                value=Decimal("300"),
                date=date.today(),
            ),
        }
        set_record = SetRecord(
            reps=5, weight=Decimal("225"), weight_unit=WeightUnit.LB
        )
        prs = detect_set_prs(set_record, "squat", date.today(), historical)

        # Should not have e1RM PR or rep_pr_5 (lower than historical)
        pr_types = {pr.pr_type for pr in prs}
        assert "e1rm" not in pr_types
        assert "rep_pr_5" not in pr_types

    def test_warmup_set_excluded(self):
        """Warmup sets should not create PRs."""
        set_record = SetRecord(
            reps=10, weight=Decimal("135"), weight_unit=WeightUnit.LB, is_warmup=True
        )
        prs = detect_set_prs(set_record, "squat", date.today(), {})
        assert len(prs) == 0

    def test_high_reps_no_e1rm_pr(self):
        """High rep sets (>12) should not create e1RM PRs."""
        set_record = SetRecord(
            reps=15, weight=Decimal("135"), weight_unit=WeightUnit.LB
        )
        prs = detect_set_prs(set_record, "squat", date.today(), {})

        pr_types = {pr.pr_type for pr in prs}
        assert "e1rm" not in pr_types
        # Should still have rep PRs
        assert "rep_pr_10" in pr_types

    def test_improvement_percentage_calculated(self):
        """PR should include improvement percentage."""
        historical = {
            "e1rm": PRRecord(
                exercise_id="squat",
                pr_type="e1rm",
                value=Decimal("300"),
                date=date.today(),
            )
        }
        set_record = SetRecord(
            reps=1, weight=Decimal("315"), weight_unit=WeightUnit.LB
        )
        prs = detect_set_prs(set_record, "squat", date.today(), historical)

        e1rm_pr = next(pr for pr in prs if pr.pr_type == "e1rm")
        assert e1rm_pr.previous_value == Decimal("300")
        assert e1rm_pr.improvement_pct == pytest.approx(5.0, abs=0.1)


class TestDetectExercisePRs:
    """Tests for detect_exercise_prs function."""

    def test_multiple_sets_best_pr_kept(self):
        """When multiple sets could be PRs, only best is kept."""
        performance = ExercisePerformance(
            exercise_name="Squat",
            canonical_id="squat",
            sets=[
                SetRecord(reps=5, weight=Decimal("225"), weight_unit=WeightUnit.LB),
                SetRecord(reps=5, weight=Decimal("235"), weight_unit=WeightUnit.LB),
                SetRecord(reps=5, weight=Decimal("245"), weight_unit=WeightUnit.LB),
            ],
        )
        prs = detect_exercise_prs(performance, date.today(), {})

        # Should only have one e1RM PR (from the 245 set)
        e1rm_prs = [pr for pr in prs if pr.pr_type == "e1rm"]
        assert len(e1rm_prs) == 1
        assert e1rm_prs[0].weight == Decimal("245")


class TestDetectSessionPRs:
    """Tests for detect_session_prs function."""

    def test_multiple_exercises(self):
        """Should detect PRs across multiple exercises."""
        session = WorkoutSession(
            date=date.today(),
            exercises=[
                ExercisePerformance(
                    exercise_name="Squat",
                    canonical_id="squat",
                    sets=[SetRecord(reps=5, weight=Decimal("275"), weight_unit=WeightUnit.LB)],
                ),
                ExercisePerformance(
                    exercise_name="Bench Press",
                    canonical_id="bench_press",
                    sets=[SetRecord(reps=5, weight=Decimal("185"), weight_unit=WeightUnit.LB)],
                ),
            ],
        )
        prs = detect_session_prs(session, {})

        exercise_ids = {pr.exercise_id for pr in prs}
        assert "squat" in exercise_ids
        assert "bench_press" in exercise_ids


class TestBuildPRHistory:
    """Tests for build_pr_history function."""

    def test_builds_from_set_data(self):
        """Should build PR records from historical data."""
        sets_data = [
            {"weight_lb": 225, "reps": 5, "session_date": "2024-01-01", "is_warmup": False},
            {"weight_lb": 235, "reps": 5, "session_date": "2024-01-08", "is_warmup": False},
            {"weight_lb": 245, "reps": 5, "session_date": "2024-01-15", "is_warmup": False},
        ]
        prs = build_pr_history(sets_data, "squat")

        assert "e1rm" in prs
        assert "rep_pr_5" in prs
        # Best weight should be 245
        assert prs["rep_pr_5"].value == Decimal("245")

    def test_excludes_warmups(self):
        """Should exclude warmup sets."""
        sets_data = [
            {"weight_lb": 135, "reps": 10, "session_date": "2024-01-01", "is_warmup": True},
            {"weight_lb": 225, "reps": 5, "session_date": "2024-01-01", "is_warmup": False},
        ]
        prs = build_pr_history(sets_data, "squat")

        # rep_pr_10 should not exist (only warmup had 10 reps)
        assert "rep_pr_10" not in prs


class TestFormatPRForDisplay:
    """Tests for format_pr_for_display function."""

    def test_e1rm_format(self):
        """e1RM PR should display correctly."""
        pr = PRRecord(
            exercise_id="squat",
            pr_type="e1rm",
            value=Decimal("315"),
            date=date.today(),
            weight=Decimal("275"),
            reps=5,
            improvement_pct=5.0,
        )
        result = format_pr_for_display(pr)
        assert "315" in result
        assert "275" in result
        assert "5" in result
        assert "+5.0%" in result

    def test_rep_pr_format(self):
        """Rep PR should display correctly."""
        pr = PRRecord(
            exercise_id="squat",
            pr_type="rep_pr_5",
            value=Decimal("245"),
            date=date.today(),
            weight=Decimal("245"),
            reps=5,
        )
        result = format_pr_for_display(pr)
        assert "5+ rep" in result
        assert "245" in result
