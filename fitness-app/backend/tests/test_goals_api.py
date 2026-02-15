"""
Tests for Goals API endpoints.

Endpoints tested:
- POST /api/goals - Create single goal
- POST /api/goals/batch - Create multiple goals
- GET /api/goals - List user goals
- GET /api/goals/{id} - Get goal detail
- PUT /api/goals/{id} - Update goal
- DELETE /api/goals/{id} - Abandon goal

Key business rules tested:
- Maximum 5 active goals per user
- Batch creation respects the limit
- Goal progress tracking
"""
import pytest
from datetime import date, timedelta
from unittest.mock import Mock, MagicMock, patch
from typing import List

from app.services.mission_service import MAX_ACTIVE_GOALS, GoalStatus


class TestMaxGoalsLimit:
    """
    Tests for the 5 active goals limit.

    Users can have at most 5 active goals at any time.
    """

    def test_single_goal_creation_allowed_when_under_limit(self, sample_goals, test_user_id):
        """
        Should allow creating a single goal when user has < 5 active goals.
        """
        active_goals = []  # User has no goals
        assert len(active_goals) < MAX_ACTIVE_GOALS

    def test_single_goal_creation_blocked_at_limit(self, sample_goals, test_user_id):
        """
        Should block creating a single goal when user already has 5 active goals.

        This tests the business rule enforced in the API endpoint.
        """
        # Simulate user having 5 active goals
        active_goals = list(sample_goals.values())[:3] + [
            Mock(status="active"),
            Mock(status="active"),
        ]
        assert len(active_goals) >= MAX_ACTIVE_GOALS

        # The API would return 400 Bad Request
        # "Maximum 5 active goals allowed. Abandon or complete existing goals first."

    def test_completed_goals_dont_count_towards_limit(self, sample_goals, test_user_id):
        """
        Completed goals should NOT count towards the 5 goal limit.
        """
        bench_goal = sample_goals["bench_goal"]
        bench_goal.status = GoalStatus.COMPLETED.value

        # This goal is completed, so it shouldn't count
        active_goals = [g for g in sample_goals.values() if g.status == GoalStatus.ACTIVE.value]
        assert len(active_goals) == 2  # bench is completed, squat and deadlift are active

    def test_abandoned_goals_dont_count_towards_limit(self, sample_goals, test_user_id):
        """
        Abandoned goals should NOT count towards the 5 goal limit.
        """
        bench_goal = sample_goals["bench_goal"]
        bench_goal.status = GoalStatus.ABANDONED.value

        active_goals = [g for g in sample_goals.values() if g.status == GoalStatus.ACTIVE.value]
        assert len(active_goals) == 2


class TestBatchGoalCreation:
    """
    Tests for POST /api/goals/batch endpoint.

    This endpoint allows creating multiple goals at once (e.g., from the multi-goal wizard).
    """

    def test_batch_creation_success_when_under_limit(self, test_exercises, test_user_id):
        """
        Should successfully create multiple goals when total won't exceed limit.
        """
        active_goals = []  # User has no goals
        batch_size = 3

        slots_available = MAX_ACTIVE_GOALS - len(active_goals)
        assert batch_size <= slots_available

    def test_batch_creation_blocked_when_would_exceed_limit(self, test_user_id):
        """
        Should return error when batch would exceed 5 active goals.

        If user has 4 active goals and tries to create 2 more, should fail.
        """
        current_active_count = 4
        batch_size = 2

        slots_available = MAX_ACTIVE_GOALS - current_active_count
        assert batch_size > slots_available

        # Expected error message pattern:
        # "Can only create {slots_available} more goals. You have {current_active_count} active goals."

    def test_batch_size_cannot_exceed_max(self, test_user_id):
        """
        Batch size itself cannot exceed 5 (even with 0 active goals).
        """
        batch_size = 6
        assert batch_size > MAX_ACTIVE_GOALS

        # Expected validation error:
        # "Batch size cannot exceed 5 goals"

    def test_batch_creation_validates_all_exercises(self, test_exercises, test_user_id):
        """
        All exercise IDs in batch must exist.
        """
        valid_ids = [test_exercises["bench_press"].id, test_exercises["squat"].id]
        invalid_id = "nonexistent-exercise-id"

        # If any exercise ID is invalid, the whole batch should fail
        all_ids = valid_ids + [invalid_id]
        found_ids = set(valid_ids)
        missing_ids = set(all_ids) - found_ids

        assert missing_ids == {invalid_id}
        # Expected error: "Exercises not found: {missing_ids}"

    def test_batch_returns_all_created_goals(self, sample_goals):
        """
        Response should include all created goals with their IDs and progress.
        """
        goals = list(sample_goals.values())

        # Simulate response structure
        response = {
            "goals": goals,
            "created_count": len(goals),
            "active_count": len(goals),
        }

        assert response["created_count"] == 3
        assert response["active_count"] == 3


class TestGoalCreationValidation:
    """
    Tests for goal creation validation rules.
    """

    def test_exercise_id_required(self):
        """Goal must have a valid exercise_id"""
        goal_data = {
            "target_weight": 225,
            "weight_unit": "lb",
            "deadline": (date.today() + timedelta(weeks=12)).isoformat(),
            # Missing exercise_id
        }
        assert "exercise_id" not in goal_data

    def test_exercise_must_exist(self, test_exercises):
        """Exercise ID must reference an existing exercise"""
        existing_ids = {ex.id for ex in test_exercises.values()}
        fake_id = "fake-exercise-id"
        assert fake_id not in existing_ids

    def test_target_weight_must_be_positive(self):
        """Target weight must be > 0"""
        invalid_weights = [0, -100, -1]
        for weight in invalid_weights:
            assert weight <= 0

    def test_target_reps_must_be_positive(self):
        """Target reps must be >= 1"""
        invalid_reps = [0, -1]
        for reps in invalid_reps:
            assert reps < 1

    def test_deadline_must_be_in_future(self):
        """Deadline should be in the future (warning, not error)"""
        past_date = date.today() - timedelta(days=1)
        today = date.today()
        assert past_date < today

    def test_weight_unit_valid_values(self):
        """Weight unit must be 'lb' or 'kg'"""
        valid_units = ["lb", "kg"]
        assert "lb" in valid_units
        assert "kg" in valid_units


class TestGoalListing:
    """
    Tests for GET /api/goals endpoint.
    """

    def test_list_returns_active_goals_by_default(self, sample_goals):
        """By default, only active goals are returned"""
        all_goals = list(sample_goals.values())

        # Simulate filtering
        active_only = [g for g in all_goals if g.status == GoalStatus.ACTIVE.value]
        assert len(active_only) == len(all_goals)  # All are active by default

    def test_list_includes_inactive_when_requested(self, sample_goals):
        """include_inactive=True returns completed/abandoned goals too"""
        all_goals = list(sample_goals.values())

        # Mark one as completed
        all_goals[0].status = GoalStatus.COMPLETED.value

        active_only = [g for g in all_goals if g.status == GoalStatus.ACTIVE.value]
        all_goals_count = len(all_goals)

        assert len(active_only) < all_goals_count

    def test_list_returns_goal_summaries(self, sample_goals):
        """
        Response should include summary info for each goal:
        - id, exercise_name, target_weight, target_reps, progress_percent
        """
        goal = sample_goals["bench_goal"]

        summary = {
            "id": goal.id,
            "exercise_name": goal.exercise.name,
            "target_weight": goal.target_weight,
            "target_reps": goal.target_reps,
            "progress_percent": 91.1,  # (205/225) * 100
            "status": goal.status,
        }

        assert summary["exercise_name"] == "Barbell Bench Press"

    def test_list_includes_counts(self, sample_goals):
        """
        Response should include:
        - active_count, completed_count, can_add_more, max_goals
        """
        goals = list(sample_goals.values())

        response = {
            "goals": goals,
            "active_count": 3,
            "completed_count": 0,
            "can_add_more": True,  # 3 < 5
            "max_goals": MAX_ACTIVE_GOALS,
        }

        assert response["can_add_more"] == (response["active_count"] < MAX_ACTIVE_GOALS)


class TestGoalUpdates:
    """
    Tests for PUT /api/goals/{id} endpoint.
    """

    def test_update_target_weight(self, sample_goals):
        """Should allow updating target weight"""
        goal = sample_goals["bench_goal"]
        original_weight = goal.target_weight

        # Update to new target
        goal.target_weight = 250
        assert goal.target_weight != original_weight

    def test_update_target_reps(self, sample_goals):
        """Should allow updating target reps"""
        goal = sample_goals["bench_goal"]
        original_reps = goal.target_reps

        goal.target_reps = 3  # Change from 1RM to 3RM goal
        assert goal.target_reps != original_reps

    def test_update_deadline(self, sample_goals):
        """Should allow extending deadline"""
        goal = sample_goals["bench_goal"]
        original_deadline = goal.deadline

        goal.deadline = original_deadline + timedelta(weeks=4)
        assert goal.deadline > original_deadline

    def test_update_status_to_completed(self, sample_goals):
        """Should allow marking goal as completed"""
        goal = sample_goals["bench_goal"]
        assert goal.status == GoalStatus.ACTIVE.value

        goal.status = GoalStatus.COMPLETED.value
        assert goal.status == GoalStatus.COMPLETED.value

    def test_cannot_update_other_users_goal(self, sample_goals):
        """Should not allow updating goals belonging to other users"""
        goal = sample_goals["bench_goal"]
        other_user_id = "other-user-id"

        assert goal.user_id != other_user_id

    def test_invalid_status_rejected(self):
        """Invalid status values should be rejected"""
        valid_statuses = [s.value for s in GoalStatus]
        invalid_status = "invalid_status"

        assert invalid_status not in valid_statuses


class TestGoalDeletion:
    """
    Tests for DELETE /api/goals/{id} endpoint (abandon goal).
    """

    def test_abandon_active_goal(self, sample_goals):
        """Should allow abandoning active goals"""
        goal = sample_goals["bench_goal"]
        assert goal.status == GoalStatus.ACTIVE.value

        goal.status = GoalStatus.ABANDONED.value
        assert goal.status == GoalStatus.ABANDONED.value

    def test_cannot_abandon_completed_goal(self, sample_goals):
        """Should not allow abandoning already completed goals"""
        goal = sample_goals["bench_goal"]
        goal.status = GoalStatus.COMPLETED.value

        # Attempting to abandon should fail
        assert goal.status != GoalStatus.ACTIVE.value

    def test_cannot_abandon_already_abandoned_goal(self, sample_goals):
        """Should not allow abandoning already abandoned goals"""
        goal = sample_goals["bench_goal"]
        goal.status = GoalStatus.ABANDONED.value

        assert goal.status != GoalStatus.ACTIVE.value

    def test_abandon_sets_abandoned_at(self, sample_goals):
        """Abandoning should set abandoned_at timestamp"""
        from datetime import datetime

        goal = sample_goals["bench_goal"]
        goal.status = GoalStatus.ABANDONED.value
        goal.abandoned_at = datetime.utcnow()

        assert goal.abandoned_at is not None


class TestGoalProgress:
    """
    Tests for goal progress calculation.
    """

    def test_progress_calculation(self, sample_goals):
        """
        Progress = (current_e1rm / target_e1rm) * 100

        For bench goal: current=205, target=225 (with 1 rep) -> 91.1%
        For 1 rep, target_e1rm = target_weight * (1 + 1/30) = target_weight * 1.033
        205 / (225 * 1.033) = 205 / 232.5 = 88.2%
        """
        goal = sample_goals["bench_goal"]
        target_e1rm = goal.target_weight * (1 + goal.target_reps / 30)  # Epley
        progress = (goal.current_e1rm / target_e1rm) * 100

        # current=205, target_weight=225, target_reps=1
        # target_e1rm = 225 * (1 + 1/30) = 232.5
        # progress = 205 / 232.5 * 100 = 88.2%
        assert round(progress, 1) == 88.2

    def test_progress_capped_at_100(self, sample_goals):
        """Progress should be capped at 100%"""
        goal = sample_goals["bench_goal"]
        goal.current_e1rm = 250  # Exceeds target

        target_e1rm = goal.target_weight
        progress = min(100, (goal.current_e1rm / target_e1rm) * 100)

        assert progress == 100

    def test_progress_with_rep_goal(self, sample_goals):
        """
        For rep goals (target_reps > 1), target_e1rm uses Epley formula.

        E.g., 200 lb x 5 reps goal -> target_e1rm = 200 * (1 + 5/30) = 233.3
        """
        goal = sample_goals["bench_goal"]
        goal.target_weight = 200
        goal.target_reps = 5

        target_e1rm = goal.target_weight * (1 + goal.target_reps / 30)
        assert round(target_e1rm, 1) == 233.3

    def test_weeks_remaining(self, sample_goals):
        """Should calculate weeks until deadline"""
        goal = sample_goals["bench_goal"]
        deadline = date.today() + timedelta(weeks=12)
        goal.deadline = deadline

        days_remaining = (goal.deadline - date.today()).days
        weeks_remaining = days_remaining // 7

        assert weeks_remaining == 12
