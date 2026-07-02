"""
Tests for multi-goal mission functionality.

The mission system generates weekly training plans that work towards user goals.
With multi-goal support, missions can target up to 5 goals simultaneously.

Key functionality tested:
- Training split determination (PPL, Upper/Lower, Full Body)
- e1RM calculation and prescription weight math
- Workout template generation per split
- Mission backfill for stale/incomplete missions

End-to-end mission API behavior (generation, accept, goal progress) lives in
tests/test_missions_api.py.
"""
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.models.mission import TrainingSplit
from app.services import mission_service
from app.services.mission_service import (
    MAX_ACTIVE_GOALS,
    _generate_ppl_workouts,
    _generate_same_group_workouts,
    _generate_single_focus_workouts,
    _get_projected_e1rm,
    _prescribed_weight,
    backfill_current_mission,
    calculate_e1rm,
    determine_training_split,
    generate_multi_goal_mission,
    get_muscle_group,
    needs_backfill,
    weeks_until,
)
from tests.conftest import (
    MockExercise,
    MockGoal,
    create_goal,
)


@pytest.fixture(autouse=True)
def _clear_exercise_id_cache():
    """
    mission_service._exercise_id_cache is a module-level global. The backfill
    test runs the service against a Mock db, which caches Mock objects as
    exercise ids — clear it around every test so no Mock leaks across tests.
    """
    mission_service._exercise_id_cache.clear()
    yield
    mission_service._exercise_id_cache.clear()


class TestGetMuscleGroup:
    """
    Tests for get_muscle_group() function.

    This function determines if an exercise is Push, Pull, or Legs.
    """

    def test_push_exercises(self):
        """Chest, shoulders, triceps exercises should be 'push'"""
        push_exercises = [
            "Bench Press",
            "Incline Bench Press",
            "Overhead Press",
            "Shoulder Press",
            "Dumbbell Press",
            "Tricep Extension",
            "Chest Fly",
            "Dips",
        ]
        for name in push_exercises:
            result = get_muscle_group(name)
            assert result == "push", f"'{name}' should be 'push', got '{result}'"

    def test_pull_exercises(self):
        """Back, biceps exercises should be 'pull'"""
        pull_exercises = [
            "Deadlift",
            "Barbell Row",
            "Bent Over Row",
            "Pull-up",
            "Lat Pulldown",
            "Bicep Curl",
            "Face Pull",
        ]
        for name in pull_exercises:
            result = get_muscle_group(name)
            assert result == "pull", f"'{name}' should be 'pull', got '{result}'"

    def test_leg_exercises(self):
        """Quad, hamstring, glute exercises should be 'legs'"""
        # Keywords are checked longest-first, so specific matches like
        # "leg curl" and "romanian deadlift" take precedence over generic
        # matches like "curl" and "deadlift".
        leg_exercises = [
            "Squat",
            "Front Squat",
            "Leg Press",
            "Leg Extension",
            "Leg Curl",
            "Romanian Deadlift",
            "Hip Thrust",
            "Lunges",
            "Calf Raises",
        ]
        for name in leg_exercises:
            result = get_muscle_group(name)
            assert result == "legs", f"'{name}' should be 'legs', got '{result}'"

    def test_unknown_exercises_default_to_full_body(self):
        """Unknown exercises should default to 'full_body'"""
        unknown_exercises = [
            "Custom Exercise",
            "Mystery Movement",
            "asdfghjkl",
        ]
        for name in unknown_exercises:
            result = get_muscle_group(name)
            assert result == "full_body", f"'{name}' should be 'full_body', got '{result}'"


class TestDetermineTrainingSplit:
    """
    Tests for determine_training_split() function.

    This function determines the optimal training split based on goal exercises:
    - SINGLE_FOCUS: 1 goal
    - PPL: Push + Pull + Legs goals (Big Three)
    - UPPER_LOWER: Only upper body or mixed without all three
    - FULL_BODY: All goals share one muscle group (rotating focus)
    """

    def test_single_goal_returns_single_focus(self, sample_goals):
        """Single goal should use SINGLE_FOCUS split"""
        goals = [sample_goals["bench_goal"]]
        split = determine_training_split(goals)
        assert split == TrainingSplit.SINGLE_FOCUS

    def test_big_three_returns_ppl(self, sample_goals):
        """
        Bench (Push) + Deadlift (Pull) + Squat (Legs) should use PPL split.
        """
        goals = [
            sample_goals["bench_goal"],    # Push
            sample_goals["deadlift_goal"], # Pull
            sample_goals["squat_goal"],    # Legs
        ]
        split = determine_training_split(goals)
        assert split == TrainingSplit.PPL

    def test_upper_body_only_returns_upper_lower(self, test_exercises, test_user_id):
        """
        Only push + pull goals (no legs) should use UPPER_LOWER split.
        """
        bench = test_exercises["bench_press"]
        row = test_exercises["row"]

        goals = [
            create_goal(test_user_id, bench, 225),
            create_goal(test_user_id, row, 185),
        ]

        split = determine_training_split(goals)
        assert split == TrainingSplit.UPPER_LOWER

    @pytest.mark.parametrize(
        "exercise_keys",
        [
            pytest.param(("squat", "front_squat"), id="legs-only"),
            pytest.param(("bench_press", "incline_bench"), id="push-only"),
        ],
    )
    def test_same_muscle_group_goals_return_full_body(
        self, test_exercises, test_user_id, exercise_keys
    ):
        """
        All goals in a single muscle group deterministically use the
        FULL_BODY (rotating-focus) split.
        """
        goals = [create_goal(test_user_id, test_exercises[k], 225) for k in exercise_keys]
        split = determine_training_split(goals)
        assert split == TrainingSplit.FULL_BODY


class TestCalculateE1rm:
    """
    Tests for calculate_e1rm() function (Epley formula).

    e1RM = weight * (1 + reps/30)
    """

    def test_one_rep_equals_weight(self):
        """For 1 rep, e1RM equals the weight"""
        assert calculate_e1rm(225, 1) == 225
        assert calculate_e1rm(100, 1) == 100

    def test_epley_formula(self):
        """Verify Epley formula calculation"""
        # 200 lb x 5 reps = 200 * (1 + 5/30) = 200 * 1.167 = 233.3
        result = calculate_e1rm(200, 5)
        assert round(result, 1) == 233.3

        # 225 lb x 3 reps = 225 * (1 + 3/30) = 225 * 1.1 = 247.5
        result = calculate_e1rm(225, 3)
        assert round(result, 1) == 247.5

    @pytest.mark.parametrize(
        ("weight", "reps"),
        [(0, 5), (-100, 5), (225, 0), (225, -1)],
        ids=["zero-weight", "negative-weight", "zero-reps", "negative-reps"],
    )
    def test_non_positive_inputs_return_zero(self, weight, reps):
        """Zero or negative weight/reps returns 0 (single guard clause)"""
        assert calculate_e1rm(weight, reps) == 0


class TestMissionPrescriptionWeights:
    def test_projected_e1rm_and_weight_rounding(self):
        """Projected e1RM should progress toward target and weights should round to nearest 5 lb."""
        exercise = MockExercise("ex-bench-001", "Barbell Bench Press", "compound")
        deadline = date.today() + timedelta(weeks=4)
        goal = MockGoal(
            id="goal-1",
            user_id="user-1",
            exercise_id=exercise.id,
            exercise=exercise,
            target_weight=250,
            target_reps=1,
            weight_unit="lb",
            deadline=deadline,
            current_e1rm=200,
            starting_e1rm=200,
        )

        projected = _get_projected_e1rm(goal)
        weeks_remaining = max(1, weeks_until(goal.deadline))
        expected = 200 + (250 - 200) / weeks_remaining
        assert projected == pytest.approx(expected, rel=1e-3)

        weight_5 = _prescribed_weight(goal, 5)
        weight_6 = _prescribed_weight(goal, 6)

        expected_5 = round((projected * 0.85) / 5) * 5
        expected_6 = round((projected * 0.82) / 5) * 5

        assert weight_5 == expected_5
        assert weight_6 == expected_6

        # When e1RM data exists it drives the prescription (not the
        # target-weight fallback): 8 weeks out, current 200 vs target 225
        # -> projected ~203, 5-rep weight (85%) rounds to exactly 175.
        goal_with_e1rm = MockGoal(
            id="goal-with-e1rm",
            user_id="user-1",
            exercise_id=exercise.id,
            exercise=exercise,
            target_weight=225,
            target_reps=1,
            weight_unit="lb",
            deadline=date.today() + timedelta(weeks=8),
            current_e1rm=200,
            starting_e1rm=180,
        )
        assert _prescribed_weight(goal_with_e1rm, 5) == 175

    def test_single_focus_workout_includes_accessory_volume_and_weights(self):
        """Single-focus missions should be 4x5, 3x8, 3x10 with weights and total sets = 10."""
        exercise = MockExercise("ex-bench-001", "Barbell Bench Press", "compound")
        goal = MockGoal(
            id="goal-3",
            user_id="user-1",
            exercise_id=exercise.id,
            exercise=exercise,
            target_weight=225,
            target_reps=1,
            weight_unit="lb",
            deadline=date.today() + timedelta(weeks=8),
            current_e1rm=185,
            starting_e1rm=185,
        )

        workouts = _generate_single_focus_workouts(goal)
        assert len(workouts) == 3

        reps_by_day = [workouts[0]["prescriptions"][0]["reps"],
                       workouts[1]["prescriptions"][0]["reps"],
                       workouts[2]["prescriptions"][0]["reps"]]
        assert reps_by_day == [5, 8, 10]

        total_sets = sum(p["sets"] for w in workouts for p in w["prescriptions"])
        assert total_sets == 10

        for workout in workouts:
            for prescription in workout["prescriptions"]:
                assert prescription["weight"] is not None


class TestMissionBackfill:
    def test_needs_backfill_for_missing_weights(self):
        """If any prescription has no weight and no workouts completed, backfill is needed."""
        exercise = MockExercise("ex-bench-001", "Barbell Bench Press", "compound")
        goal = MockGoal(
            id="goal-1",
            user_id="user-1",
            exercise_id=exercise.id,
            exercise=exercise,
            target_weight=225,
            target_reps=1,
            weight_unit="lb",
        )
        mission_goal = SimpleNamespace(goal_id=goal.id, goal=goal)
        mission = SimpleNamespace(
            workouts=[
                SimpleNamespace(
                    status="pending",
                    focus="Heavy Barbell Bench Press",
                    day_number=1,
                    prescriptions=[SimpleNamespace(weight=None)]
                )
            ],
            mission_goals=[mission_goal],
            goal=None
        )

        assert needs_backfill(mission, [goal]) is True

    def test_needs_backfill_skips_if_completed(self):
        """If any workout is completed, backfill should be skipped."""
        exercise = MockExercise("ex-bench-001", "Barbell Bench Press", "compound")
        goal = MockGoal(
            id="goal-1",
            user_id="user-1",
            exercise_id=exercise.id,
            exercise=exercise,
            target_weight=225,
            target_reps=1,
            weight_unit="lb",
        )
        mission_goal = SimpleNamespace(goal_id=goal.id, goal=goal)
        mission = SimpleNamespace(
            workouts=[
                SimpleNamespace(
                    status="completed",
                    focus="Heavy Barbell Bench Press",
                    day_number=1,
                    prescriptions=[SimpleNamespace(weight=None)]
                )
            ],
            mission_goals=[mission_goal],
            goal=None
        )

        assert needs_backfill(mission, [goal]) is False

    def test_backfill_adds_accessory_prescriptions(self):
        """Backfill should populate accessory day prescriptions for single-goal missions."""
        exercise = MockExercise("ex-bench-001", "Barbell Bench Press", "compound")
        goal = MockGoal(
            id="goal-1",
            user_id="user-1",
            exercise_id=exercise.id,
            exercise=exercise,
            target_weight=225,
            target_reps=1,
            weight_unit="lb",
        )

        mission = SimpleNamespace(
            id="mission-1",
            goal_id=goal.id,
            training_split="single_focus",
            weekly_target=None,
            coaching_message=None,
            mission_goals=[SimpleNamespace(goal_id=goal.id, goal=goal)],
            workouts=[
                SimpleNamespace(
                    id="workout-1",
                    day_number=1,
                    focus="Heavy Barbell Bench Press",
                    primary_lift="Barbell Bench Press",
                    status="pending",
                    prescriptions=[]
                ),
                SimpleNamespace(
                    id="workout-2",
                    day_number=2,
                    focus="Accessory Work",
                    primary_lift=None,
                    status="pending",
                    prescriptions=[]
                ),
                SimpleNamespace(
                    id="workout-3",
                    day_number=3,
                    focus="Volume Barbell Bench Press",
                    primary_lift="Barbell Bench Press",
                    status="pending",
                    prescriptions=[]
                ),
            ]
        )

        db = Mock()
        db.add = Mock()
        db.delete = Mock()
        db.flush = Mock()

        updated = backfill_current_mission(db, mission, [goal])
        accessory = [w for w in updated.workouts if "accessory" in w.focus.lower()][0]
        assert len(accessory.prescriptions) > 0
        assert accessory.prescriptions[0].reps == 8


class TestSameGroupRotation:
    def test_same_group_rotation_includes_all_goals(self):
        """Two push goals should appear across all three days with rotation."""
        bench = MockExercise("ex-bench-001", "Barbell Bench Press", "compound")
        incline = MockExercise("ex-bench-002", "Incline Bench Press", "compound")
        goal_a = MockGoal(
            id="goal-a",
            user_id="user-1",
            exercise_id=bench.id,
            exercise=bench,
            target_weight=225,
            weight_unit="lb",
        )
        goal_b = MockGoal(
            id="goal-b",
            user_id="user-1",
            exercise_id=incline.id,
            exercise=incline,
            target_weight=185,
            weight_unit="lb",
        )

        workouts = _generate_same_group_workouts([goal_a, goal_b])
        assert len(workouts) == 3

        day1_ids = {p["exercise_id"] for p in workouts[0]["prescriptions"]}
        day2_ids = {p["exercise_id"] for p in workouts[1]["prescriptions"]}
        day3_ids = {p["exercise_id"] for p in workouts[2]["prescriptions"]}

        assert goal_a.exercise_id in day1_ids
        assert goal_b.exercise_id in day1_ids
        assert goal_a.exercise_id in day2_ids
        assert goal_b.exercise_id in day2_ids
        assert goal_a.exercise_id in day3_ids
        assert goal_b.exercise_id in day3_ids


class TestMultiGoalMissionGeneration:
    """
    Tests for generate_multi_goal_mission() function.
    """

    def test_mission_requires_at_least_one_goal(self, mock_db_session, test_user_id):
        """Should raise error if no goals provided"""
        with pytest.raises(ValueError, match="At least one goal is required"):
            generate_multi_goal_mission(
                mock_db_session,
                test_user_id,
                [],  # Empty goals list
                date.today(),
                date.today() + timedelta(days=6)
            )


class TestMissionEdgeCases:
    """
    Edge cases and boundary conditions for mission system.
    """

    def test_mission_with_max_goals(self, test_exercises, test_user_id):
        """
        Mission with 5 goals (max) should work correctly.

        The first 5 test exercises span push (3x bench variants) and legs
        (squat, front squat) — mixed groups with 4+ goals deterministically
        resolve to PPL.
        """
        all_exercises = list(test_exercises.values())[:5]
        goals = [create_goal(test_user_id, ex, 200) for ex in all_exercises]

        assert len(goals) == MAX_ACTIVE_GOALS

        split = determine_training_split(goals)
        assert split == TrainingSplit.PPL


class TestPPLWorkoutGeneration:
    """
    Tests for _generate_ppl_workouts() function.

    PPL should only generate workout days for categories that have goals.
    """

    def test_ppl_with_all_three_categories(self, test_exercises, test_user_id):
        """
        PPL with push, pull, and legs goals should generate 3 workout days.
        """
        bench = test_exercises["bench_press"]  # Push
        deadlift = test_exercises["deadlift"]  # Pull
        squat = test_exercises["squat"]        # Legs

        goals = [
            create_goal(test_user_id, bench, 225),
            create_goal(test_user_id, deadlift, 405),
            create_goal(test_user_id, squat, 315),
        ]

        workouts = _generate_ppl_workouts(goals)

        assert len(workouts) == 3
        assert workouts[0]["day"] == 1
        assert workouts[1]["day"] == 2
        assert workouts[2]["day"] == 3
        # All days should have prescriptions
        for w in workouts:
            assert len(w["prescriptions"]) > 0

    @pytest.mark.parametrize(
        ("exercise_keys", "expected_focus_prefixes"),
        [
            pytest.param(["bench_press"], ["Push"], id="push-only-one-day"),
            pytest.param(["bench_press", "squat"], ["Push", "Legs"], id="push-legs-two-days"),
        ],
    )
    def test_ppl_filters_empty_days(
        self, test_exercises, test_user_id, exercise_keys, expected_focus_prefixes
    ):
        """
        PPL with goals in only some categories should drop the empty days
        and renumber the remaining days from 1.
        """
        goals = [create_goal(test_user_id, test_exercises[k], 225) for k in exercise_keys]

        workouts = _generate_ppl_workouts(goals)

        assert len(workouts) == len(expected_focus_prefixes)
        assert [w["day"] for w in workouts] == list(range(1, len(workouts) + 1))
        for workout, prefix in zip(workouts, expected_focus_prefixes):
            assert workout["focus"].startswith(prefix)
            assert len(workout["prescriptions"]) > 0


class TestWeightFallback:
    """Tests for weight fallback when no e1RM data exists."""

    def test_weight_fallback_uses_target_weight(self):
        """If no e1RM data, should use 85% of target as base for progression."""
        exercise = MockExercise("ex-bench-001", "Barbell Bench Press", "compound")
        deadline = date.today() + timedelta(weeks=8)

        # Goal with NO e1RM data
        goal = MockGoal(
            id="goal-no-e1rm",
            user_id="user-1",
            exercise_id=exercise.id,
            exercise=exercise,
            target_weight=200,  # Target is 200 lb
            target_reps=1,
            weight_unit="lb",
            deadline=deadline,
            current_e1rm=None,  # No current e1RM
            starting_e1rm=None,  # No starting e1RM
        )

        # The weight should NOT be None thanks to fallback in _get_projected_e1rm
        weight = _prescribed_weight(goal, 5)
        assert weight is not None

        # Calculation:
        # - target_e1rm = 200 (for 1 rep)
        # - base_e1rm = 0.85 * 200 = 170 (fallback when no e1RM data)
        # - weeks_remaining = 8
        # - projected_e1rm = 170 + (200 - 170) / 8 = 173.75
        # - intensity for 5 reps = 0.85
        # - weight = 173.75 * 0.85 = 147.69, rounded to 150
        assert weight == 150

    def test_weight_fallback_with_zero_target_returns_none(self):
        """If target weight is 0 or None, weight should be None."""
        exercise = MockExercise("ex-bench-001", "Barbell Bench Press", "compound")
        deadline = date.today() + timedelta(weeks=8)

        goal = MockGoal(
            id="goal-bad",
            user_id="user-1",
            exercise_id=exercise.id,
            exercise=exercise,
            target_weight=0,  # Invalid target
            target_reps=1,
            weight_unit="lb",
            deadline=deadline,
            current_e1rm=None,
            starting_e1rm=None,
        )

        weight = _prescribed_weight(goal, 5)
        assert weight is None


class TestAccessoryTemplates:
    """Tests for accessory exercise template system."""

    def test_accessory_template_shape(self):
        """
        Static-shape lint of the accessory template data: templates exist for
        the main groups, each entry has the required fields, retrieval
        respects the limit, and volume-day variants average higher reps.
        """
        from app.services.accessory_templates import (
            ACCESSORY_TEMPLATES,
            VOLUME_ACCESSORY_TEMPLATES,
            get_accessories_for_group,
        )

        for group in ("push", "pull", "legs"):
            assert group in ACCESSORY_TEMPLATES, f"Missing templates for {group}"
            assert len(ACCESSORY_TEMPLATES[group]) >= 3
            for acc in ACCESSORY_TEMPLATES[group]:
                for field in ("exercise_name", "sets", "reps", "weight_pct"):
                    assert field in acc, f"Missing {field} in {group} accessory"

            fetched = get_accessories_for_group(group, is_volume_day=False, limit=4)
            assert 0 < len(fetched) <= 4

        # Volume-day templates exist and skew toward higher reps than heavy-day.
        assert "push" in VOLUME_ACCESSORY_TEMPLATES
        heavy_push = ACCESSORY_TEMPLATES["push"]
        volume_push = VOLUME_ACCESSORY_TEMPLATES["push"]
        heavy_avg_reps = sum(a["reps"] for a in heavy_push) / len(heavy_push)
        volume_avg_reps = sum(a["reps"] for a in volume_push) / len(volume_push)
        assert volume_avg_reps >= heavy_avg_reps

    def test_get_accessories_for_unknown_group_returns_empty(self):
        """Unknown muscle groups should return empty list."""
        from app.services.accessory_templates import get_accessories_for_group

        unknown_acc = get_accessories_for_group("full_body", is_volume_day=False)
        assert unknown_acc == []

        random_acc = get_accessories_for_group("arms", is_volume_day=False)
        assert random_acc == []

    def test_get_accessory_group_mapping(self):
        """Verify exercise name to group mapping works correctly."""
        from app.services.accessory_templates import get_accessory_group

        assert get_accessory_group("Barbell Bench Press") == "push"
        assert get_accessory_group("Incline Dumbbell Press") == "push"
        assert get_accessory_group("Barbell Deadlift") == "pull"
        assert get_accessory_group("Lat Pulldown") == "pull"
        assert get_accessory_group("Barbell Back Squat") == "legs"
        assert get_accessory_group("Leg Press") == "legs"
        assert get_accessory_group("Unknown Exercise") == "full_body"
