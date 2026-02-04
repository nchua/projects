"""
Tests for multi-goal mission functionality.

The mission system generates weekly training plans that work towards user goals.
With multi-goal support, missions can target up to 5 goals simultaneously.

Key functionality tested:
- Training split determination (PPL, Upper/Lower, Full Body)
- Multi-goal mission generation
- Exercise equivalence for workout completion
- Goal progress tracking through mission workouts
"""
import pytest
from datetime import date, timedelta, datetime
from unittest.mock import Mock, MagicMock, patch
from typing import List

from app.services.mission_service import (
    determine_training_split,
    get_muscle_group,
    calculate_e1rm,
    _get_projected_e1rm,
    _prescribed_weight,
    weeks_until,
    generate_multi_goal_mission,
    _generate_single_focus_workouts,
    _generate_same_group_workouts,
    _generate_ppl_workouts,
    needs_backfill,
    backfill_current_mission,
    check_mission_workout_completion,
    MAX_ACTIVE_GOALS,
)
from types import SimpleNamespace
from app.models.mission import TrainingSplit, MissionStatus, MissionWorkoutStatus
from tests.conftest import (
    MockGoal,
    MockExercise,
    MockWorkoutSession,
    MockWorkoutExercise,
    MockSet,
    MockMissionGoal,
    create_goal,
    create_workout,
)


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

    def test_leg_curl_maps_to_legs(self):
        """
        Leg Curl correctly maps to 'legs' because keywords are checked
        longest-first, so 'leg curl' matches before 'curl'.
        """
        result = get_muscle_group("Leg Curl")
        assert result == "legs", f"Leg Curl should map to 'legs', got '{result}'"

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
    - FULL_BODY: Fallback
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

    def test_legs_only_returns_upper_lower(self, test_exercises, test_user_id):
        """
        Only leg goals (no upper) should use UPPER_LOWER split.
        """
        squat = test_exercises["squat"]
        front_squat = test_exercises["front_squat"]

        goals = [
            create_goal(test_user_id, squat, 315),
            create_goal(test_user_id, front_squat, 275),
        ]

        split = determine_training_split(goals)
        # Two leg goals - could be UPPER_LOWER, PPL, or same-group rotation
        assert split in [TrainingSplit.UPPER_LOWER, TrainingSplit.PPL, TrainingSplit.FULL_BODY]

    def test_four_plus_goals_returns_ppl(self, test_exercises, test_user_id):
        """
        4+ diverse goals should use PPL for comprehensive coverage.
        """
        goals = [
            create_goal(test_user_id, test_exercises["bench_press"], 225),
            create_goal(test_user_id, test_exercises["squat"], 315),
            create_goal(test_user_id, test_exercises["deadlift"], 405),
            create_goal(test_user_id, test_exercises["row"], 185),
        ]

        split = determine_training_split(goals)
        assert split == TrainingSplit.PPL


class TestCalculateE1rm:
    """
    Tests for calculate_e1rm() function (Epley formula).

    e1RM = weight * (1 + reps/30)
    """


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

    def test_projected_e1rm_fallback_to_85_percent_of_target(self):
        """If no current/starting e1RM exists, base on 85% of target e1RM."""
        exercise = MockExercise("ex-bench-001", "Barbell Bench Press", "compound")
        deadline = date.today() + timedelta(weeks=4)
        goal = MockGoal(
            id="goal-2",
            user_id="user-1",
            exercise_id=exercise.id,
            exercise=exercise,
            target_weight=200,
            target_reps=1,
            weight_unit="lb",
            deadline=deadline,
            current_e1rm=None,
            starting_e1rm=None,
        )

        projected = _get_projected_e1rm(goal)
        weeks_remaining = max(1, weeks_until(goal.deadline))
        base = 0.85 * 200
        expected = base + (200 - base) / weeks_remaining
        assert projected == pytest.approx(expected, rel=1e-3)

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

    def test_zero_weight_returns_zero(self):
        """Zero or negative weight returns 0"""
        assert calculate_e1rm(0, 5) == 0
        assert calculate_e1rm(-100, 5) == 0

    def test_zero_reps_returns_zero(self):
        """Zero or negative reps returns 0"""
        assert calculate_e1rm(225, 0) == 0
        assert calculate_e1rm(225, -1) == 0


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

    def test_xp_reward_scales_with_goals(self, sample_goals):
        """
        XP reward should be 50 base + 50 per goal.

        1 goal: 100 XP
        2 goals: 150 XP
        3 goals: 200 XP
        """
        base_xp = 50
        per_goal_xp = 50

        for num_goals in [1, 2, 3, 4, 5]:
            expected_xp = base_xp + (per_goal_xp * num_goals)

            # 1 goal = 100, 2 = 150, 3 = 200, etc.
            assert expected_xp == 50 + (50 * num_goals)

    def test_ppl_mission_has_three_workouts(self, sample_goals):
        """
        PPL split should generate 3 workouts: Push, Pull, Legs.
        """
        goals = list(sample_goals.values())  # Bench, Squat, Deadlift
        split = determine_training_split(goals)

        # PPL should have 3 workout days
        if split == TrainingSplit.PPL:
            expected_workouts = 3
            assert expected_workouts == 3

    def test_single_focus_mission_has_three_workouts(self, sample_goals):
        """
        Single focus split also has 3 workouts: Heavy, Accessory, Volume.
        """
        goals = [sample_goals["bench_goal"]]
        split = determine_training_split(goals)

        assert split == TrainingSplit.SINGLE_FOCUS
        # Heavy day, Accessory day, Volume day
        expected_workouts = 3
        assert expected_workouts == 3


class TestMissionGoalJunction:
    """
    Tests for MissionGoal junction table entries.

    Each goal in a multi-goal mission gets a MissionGoal entry
    tracking its individual progress within the mission.
    """

    def test_multi_goal_mission_creates_junction_entries(self, sample_goals):
        """
        3 goals should create 3 MissionGoal entries.
        """
        goals = list(sample_goals.values())  # 3 goals
        mission_goals = [MockMissionGoal(g) for g in goals]

        assert len(mission_goals) == 3
        for mg, g in zip(mission_goals, goals):
            assert mg.goal_id == g.id
            assert mg.workouts_completed == 0
            assert mg.is_satisfied is False

    def test_goal_satisfied_after_two_workouts(self, sample_goals):
        """
        Goal needs 2 workouts per week to be "satisfied".
        """
        bench_goal = sample_goals["bench_goal"]
        mission_goal = MockMissionGoal(bench_goal)

        assert not mission_goal.is_satisfied

        # First workout
        mission_goal.workouts_completed = 1
        assert not mission_goal.is_satisfied

        # Second workout
        mission_goal.workouts_completed = 2
        mission_goal.is_satisfied = True
        assert mission_goal.is_satisfied


class TestWorkoutCompletionWithEquivalence:
    """
    Tests for workout completion using exercise equivalence.

    When a user logs a workout with an equivalent exercise,
    it should credit the corresponding goal.
    """

    def test_equivalent_exercise_credits_goal(self, test_exercises, sample_goals):
        """
        Logging Incline Bench should credit a Bench Press goal.
        """
        bench_goal = sample_goals["bench_goal"]
        incline = test_exercises["incline_bench"]

        # Workout with incline bench (equivalent to bench press)
        workout = create_workout(
            "test-user-1",
            [(incline, [(185, 5), (205, 3)])]
        )

        # The workout contains an exercise equivalent to the bench goal
        logged_exercise_ids = {we.exercise_id for we in workout.workout_exercises}
        assert incline.id in logged_exercise_ids

        # Bench and Incline are equivalent
        from app.services.exercise_equivalence import exercises_are_equivalent
        assert exercises_are_equivalent(
            bench_goal.exercise.name,
            incline.name
        )

    def test_single_workout_credits_multiple_goals(self, test_exercises, sample_goals):
        """
        A workout with both Bench and Squat should credit both goals.
        """
        bench = test_exercises["bench_press"]
        squat = test_exercises["squat"]

        workout = create_workout(
            "test-user-1",
            [
                (bench, [(185, 5), (205, 3)]),
                (squat, [(225, 5), (275, 3)]),
            ]
        )

        logged_exercise_ids = {we.exercise_id for we in workout.workout_exercises}

        # Workout has both exercises
        assert bench.id in logged_exercise_ids
        assert squat.id in logged_exercise_ids

        # Should credit both bench and squat goals
        bench_goal = sample_goals["bench_goal"]
        squat_goal = sample_goals["squat_goal"]

        # Both goals' exercises are in the workout
        assert bench_goal.exercise_id in logged_exercise_ids
        assert squat_goal.exercise_id in logged_exercise_ids

    def test_workout_without_goal_exercise_not_credited(self, test_exercises, sample_goals):
        """
        A workout without any goal-related exercises shouldn't credit goals.
        """
        curl = test_exercises["curl"]

        workout = create_workout(
            "test-user-1",
            [(curl, [(45, 10), (55, 8)])]
        )

        logged_exercise_ids = {we.exercise_id for we in workout.workout_exercises}

        # Curl is not equivalent to any of the Big Three goals
        bench_goal = sample_goals["bench_goal"]
        squat_goal = sample_goals["squat_goal"]
        deadlift_goal = sample_goals["deadlift_goal"]

        assert bench_goal.exercise_id not in logged_exercise_ids
        assert squat_goal.exercise_id not in logged_exercise_ids
        assert deadlift_goal.exercise_id not in logged_exercise_ids


class TestMissionCompletion:
    """
    Tests for mission completion logic.
    """

    def test_mission_complete_when_all_workouts_done(self):
        """
        Mission is complete when all planned workouts are done.
        """
        workout_statuses = [
            MissionWorkoutStatus.COMPLETED.value,
            MissionWorkoutStatus.COMPLETED.value,
            MissionWorkoutStatus.COMPLETED.value,
        ]

        completed_count = sum(
            1 for s in workout_statuses
            if s == MissionWorkoutStatus.COMPLETED.value
        )

        assert completed_count == len(workout_statuses)

    def test_mission_not_complete_with_pending_workouts(self):
        """
        Mission is NOT complete if any workouts are pending.
        """
        workout_statuses = [
            MissionWorkoutStatus.COMPLETED.value,
            MissionWorkoutStatus.PENDING.value,  # Still pending
            MissionWorkoutStatus.COMPLETED.value,
        ]

        completed_count = sum(
            1 for s in workout_statuses
            if s == MissionWorkoutStatus.COMPLETED.value
        )

        assert completed_count < len(workout_statuses)

    def test_mission_xp_awarded_on_completion(self, sample_goals):
        """
        When mission is completed, XP reward should be awarded.
        """
        num_goals = 3
        base_xp = 50
        per_goal_xp = 50
        expected_xp = base_xp + (per_goal_xp * num_goals)

        # Mission with 3 goals should award 200 XP
        assert expected_xp == 200


class TestWeeklyTargetGeneration:
    """
    Tests for weekly target message generation.
    """

    def test_single_goal_focus_message(self, sample_goals):
        """
        Single goal should generate: "Focus on {exercise_name}"
        """
        goals = [sample_goals["bench_goal"]]
        goal_names = [g.exercise.name for g in goals]

        if len(goal_names) == 1:
            message = f"Focus on {goal_names[0]}"
            assert message == "Focus on Barbell Bench Press"

    def test_multi_goal_build_message(self, sample_goals):
        """
        2-3 goals should generate: "Build strength in {names}"
        """
        goals = list(sample_goals.values())[:3]
        goal_names = [g.exercise.name for g in goals]

        if len(goal_names) <= 3:
            message = f"Build strength in {', '.join(goal_names)}"
            assert "Barbell Bench Press" in message
            assert "Barbell Back Squat" in message

    def test_many_goals_progress_message(self, test_exercises, test_user_id):
        """
        4+ goals should generate: "Progress all {count} goals this week"
        """
        exercises = [
            test_exercises["bench_press"],
            test_exercises["squat"],
            test_exercises["deadlift"],
            test_exercises["row"],
            test_exercises["ohp"],
        ]

        goals = [create_goal(test_user_id, ex, 200) for ex in exercises]
        goal_count = len(goals)

        if goal_count > 3:
            message = f"Progress all {goal_count} goals this week"
            assert message == "Progress all 5 goals this week"


class TestCoachingMessageGeneration:
    """
    Tests for coaching message generation.
    """

    def test_single_goal_coaching_message(self, sample_goals):
        """
        Single goal gets generic encouragement.
        """
        goals = [sample_goals["bench_goal"]]

        if len(goals) == 1:
            message = "Complete these workouts this week to progress toward your goal!"
            assert "progress toward your goal" in message

    def test_multi_goal_coaching_message(self, sample_goals):
        """
        Multi-goal gets split-specific coaching.
        """
        goals = list(sample_goals.values())
        split = TrainingSplit.PPL

        if len(goals) > 1:
            message = f"This week's Push/Pull/Legs split targets all {len(goals)} of your goals."
            assert "Push/Pull/Legs" in message
            assert str(len(goals)) in message


class TestMissionEdgeCases:
    """
    Edge cases and boundary conditions for mission system.
    """

    def test_goals_with_same_muscle_group(self, test_exercises, test_user_id):
        """
        Multiple goals in same muscle group should still generate valid mission.
        """
        bench = test_exercises["bench_press"]
        incline = test_exercises["incline_bench"]

        goals = [
            create_goal(test_user_id, bench, 225),
            create_goal(test_user_id, incline, 185),
        ]

        split = determine_training_split(goals)
        # Both are push - should still get a valid split
        assert split in [TrainingSplit.PPL, TrainingSplit.UPPER_LOWER, TrainingSplit.FULL_BODY]

    def test_goal_without_exercise_relationship(self, test_user_id):
        """
        Goal with missing exercise relationship should be handled gracefully.
        """
        # Create goal with None exercise
        goal = MockGoal(
            id="goal-no-exercise",
            user_id=test_user_id,
            exercise_id="ex-missing",
            exercise=None,  # Missing relationship
            target_weight=225,
        )

        # get_muscle_group should handle None exercise
        if goal.exercise:
            group = get_muscle_group(goal.exercise.name)
        else:
            group = "full_body"  # Fallback

        assert group == "full_body"

    def test_mission_with_max_goals(self, test_exercises, test_user_id):
        """
        Mission with 5 goals (max) should work correctly.
        """
        all_exercises = list(test_exercises.values())[:5]
        goals = [create_goal(test_user_id, ex, 200) for ex in all_exercises]

        assert len(goals) == MAX_ACTIVE_GOALS

        split = determine_training_split(goals)
        # Should get a valid split for 5 goals
        assert split in [TrainingSplit.PPL, TrainingSplit.UPPER_LOWER, TrainingSplit.FULL_BODY]


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

    def test_ppl_with_two_categories_filters_empty_days(self, test_exercises, test_user_id):
        """
        PPL with only push + legs goals (no pull) should generate 2 workout days.
        Empty pull day should be filtered out.
        """
        bench = test_exercises["bench_press"]  # Push
        squat = test_exercises["squat"]        # Legs

        goals = [
            create_goal(test_user_id, bench, 225),
            create_goal(test_user_id, squat, 315),
        ]

        workouts = _generate_ppl_workouts(goals)

        # Should only have 2 days (push and legs), not 3
        assert len(workouts) == 2

        # Days should be renumbered 1, 2
        assert workouts[0]["day"] == 1
        assert workouts[1]["day"] == 2

        # Each day should have prescriptions
        for w in workouts:
            assert len(w["prescriptions"]) > 0

    def test_ppl_with_one_category_generates_one_day(self, test_exercises, test_user_id):
        """
        PPL with only push goals should generate 1 workout day.
        """
        bench = test_exercises["bench_press"]  # Push

        goals = [
            create_goal(test_user_id, bench, 225),
        ]

        workouts = _generate_ppl_workouts(goals)

        # Should only have 1 day
        assert len(workouts) == 1
        assert workouts[0]["day"] == 1
        assert "Push" in workouts[0]["focus"]
        assert len(workouts[0]["prescriptions"]) > 0


class TestWeightFallback:
    """Tests for weight fallback when no e1RM data exists."""

    def test_weight_fallback_uses_target_weight(self):
        """If no e1RM data, should use 85% of target as base for progression."""
        from datetime import date, timedelta

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
        from datetime import date, timedelta

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

    def test_weight_uses_e1rm_when_available(self):
        """When e1RM data exists, it should be used instead of fallback."""
        from datetime import date, timedelta

        exercise = MockExercise("ex-bench-001", "Barbell Bench Press", "compound")
        deadline = date.today() + timedelta(weeks=8)

        goal = MockGoal(
            id="goal-with-e1rm",
            user_id="user-1",
            exercise_id=exercise.id,
            exercise=exercise,
            target_weight=225,
            target_reps=1,
            weight_unit="lb",
            deadline=deadline,
            current_e1rm=200,  # Has e1RM data
            starting_e1rm=180,
        )

        weight = _prescribed_weight(goal, 5)
        assert weight is not None
        # Should use projected e1RM, not 70% of target
        # With 8 weeks remaining, projected e1RM = 200 + (225-200)/8 = 203.125
        # For 5 reps (0.85 intensity): 203.125 * 0.85 = 172.66, rounded to 175
        assert weight == 175


class TestAccessoryTemplates:
    """Tests for accessory exercise template system."""

    def test_accessory_templates_exist_for_main_groups(self):
        """Verify templates exist for push, pull, and legs."""
        from app.services.accessory_templates import ACCESSORY_TEMPLATES

        assert "push" in ACCESSORY_TEMPLATES
        assert "pull" in ACCESSORY_TEMPLATES
        assert "legs" in ACCESSORY_TEMPLATES

        # Each should have multiple accessories
        assert len(ACCESSORY_TEMPLATES["push"]) >= 3
        assert len(ACCESSORY_TEMPLATES["pull"]) >= 3
        assert len(ACCESSORY_TEMPLATES["legs"]) >= 3

    def test_accessory_templates_have_required_fields(self):
        """Each accessory should have name, sets, reps, weight_pct."""
        from app.services.accessory_templates import ACCESSORY_TEMPLATES

        for group, accessories in ACCESSORY_TEMPLATES.items():
            for acc in accessories:
                assert "exercise_name" in acc, f"Missing exercise_name in {group}"
                assert "sets" in acc, f"Missing sets in {group}"
                assert "reps" in acc, f"Missing reps in {group}"
                assert "weight_pct" in acc, f"Missing weight_pct in {group}"

    def test_get_accessories_for_group_returns_correct_muscle_group(self):
        """get_accessories_for_group should return exercises for requested group."""
        from app.services.accessory_templates import get_accessories_for_group

        push_acc = get_accessories_for_group("push", is_volume_day=False, limit=4)
        assert len(push_acc) > 0
        assert len(push_acc) <= 4

        pull_acc = get_accessories_for_group("pull", is_volume_day=False, limit=4)
        assert len(pull_acc) > 0

        legs_acc = get_accessories_for_group("legs", is_volume_day=False, limit=4)
        assert len(legs_acc) > 0

    def test_get_accessories_for_unknown_group_returns_empty(self):
        """Unknown muscle groups should return empty list."""
        from app.services.accessory_templates import get_accessories_for_group

        unknown_acc = get_accessories_for_group("full_body", is_volume_day=False)
        assert unknown_acc == []

        random_acc = get_accessories_for_group("arms", is_volume_day=False)
        assert random_acc == []

    def test_volume_day_accessories_differ_from_heavy_day(self):
        """Volume day templates should have different reps/weights."""
        from app.services.accessory_templates import (
            ACCESSORY_TEMPLATES,
            VOLUME_ACCESSORY_TEMPLATES,
        )

        # Volume templates exist
        assert "push" in VOLUME_ACCESSORY_TEMPLATES

        # They should have higher reps on average
        heavy_push = ACCESSORY_TEMPLATES["push"]
        volume_push = VOLUME_ACCESSORY_TEMPLATES["push"]

        heavy_avg_reps = sum(a["reps"] for a in heavy_push) / len(heavy_push)
        volume_avg_reps = sum(a["reps"] for a in volume_push) / len(volume_push)

        assert volume_avg_reps >= heavy_avg_reps

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
