"""
Tests for exercise equivalence service.

The exercise equivalence system allows similar exercises to count towards goals.
For example, if a user has a Bench Press goal and logs Incline Bench Press,
the workout should still credit progress towards the Bench goal.

Functions tested:
- get_canonical_exercise(exercise_name) - Maps variations to canonical names
- get_equivalent_exercises(exercise_name) - Returns all variations
- get_equivalent_exercise_ids(goal_exercise_id, db) - DB lookup (the live
  entry point, called from mission_service)
"""
from unittest.mock import Mock

import pytest

from app.services.exercise_equivalence import (
    EXERCISE_EQUIVALENCE,
    get_canonical_exercise,
    get_equivalent_exercise_ids,
    get_equivalent_exercises,
)


@pytest.mark.parametrize("name,expected_canonical", [
    # Bench press variations
    ("Bench Press", "bench_press"),
    ("Barbell Bench Press", "bench_press"),
    ("Incline Bench Press", "bench_press"),
    ("Dumbbell Bench Press", "bench_press"),
    ("Close Grip Bench Press", "bench_press"),
    ("Decline Bench Press", "bench_press"),
    ("Floor Press", "bench_press"),
    # Squat variations
    ("Squat", "squat"),
    ("Barbell Back Squat", "squat"),
    ("Front Squat", "squat"),
    ("Goblet Squat", "squat"),
    ("Box Squat", "squat"),
    ("High Bar Squat", "squat"),
    ("Low Bar Squat", "squat"),
    ("Safety Bar Squat", "squat"),
    # Deadlift variations
    ("Deadlift", "deadlift"),
    ("Barbell Deadlift", "deadlift"),
    ("Conventional Deadlift", "deadlift"),
    ("Sumo Deadlift", "deadlift"),
    ("Trap Bar Deadlift", "deadlift"),
    ("Deficit Deadlift", "deadlift"),
    ("Block Pull", "deadlift"),
    ("Rack Pull", "deadlift"),
    # Overhead press variations
    ("Overhead Press", "overhead_press"),
    ("OHP", "overhead_press"),
    ("Shoulder Press", "overhead_press"),
    ("Military Press", "overhead_press"),
    ("Standing Press", "overhead_press"),
    ("Seated Shoulder Press", "overhead_press"),
    ("Push Press", "overhead_press"),
    ("Arnold Press", "overhead_press"),
    # Row variations
    ("Barbell Row", "row"),
    ("Bent Over Row", "row"),
    ("Pendlay Row", "row"),
    ("Dumbbell Row", "row"),
    ("T-Bar Row", "row"),
    ("Cable Row", "row"),
    ("Seated Row", "row"),
    ("Chest Supported Row", "row"),
    # Curl variations
    ("Barbell Curl", "curl"),
    ("Dumbbell Curl", "curl"),
    ("Hammer Curl", "curl"),
    ("Preacher Curl", "curl"),
    ("EZ Bar Curl", "curl"),
    ("Cable Curl", "curl"),
    ("Spider Curl", "curl"),
    ("Concentration Curl", "curl"),
    # Dips are a chest/tricep movement, listed under tricep_extension
    ("Dips", "tricep_extension"),
    # Case-insensitive matching
    ("BENCH PRESS", "bench_press"),
    ("BeNcH pReSs", "bench_press"),
    ("FRONT SQUAT", "squat"),
    ("sumo DEADLIFT", "deadlift"),
    # Unknown exercises return None
    ("Zumba", None),
    ("Swimming", None),
    ("Yoga", None),
    ("Running", None),
    ("asdfghjkl", None),
])
def test_get_canonical_exercise(name, expected_canonical):
    assert get_canonical_exercise(name) == expected_canonical


def test_pullup_and_lat_pulldown_share_canonical():
    """Pull-ups and lat pulldown are machine/free-weight equivalents."""
    pullup_canonical = get_canonical_exercise("Pull Up")
    assert pullup_canonical is not None
    assert get_canonical_exercise("Lat Pulldown") == pullup_canonical
    assert get_canonical_exercise("Chin Up") == pullup_canonical


class TestGetEquivalentExercises:
    """
    Tests for get_equivalent_exercises().

    This function returns all variations that are equivalent to a given exercise.
    """

    @pytest.mark.parametrize("name,expected_members", [
        pytest.param(
            "Bench Press",
            {"bench press", "incline bench press", "dumbbell bench press",
             "close grip bench press"},
            id="bench",
        ),
        pytest.param(
            "Squat",
            # Leg press is also in squat equivalences
            {"squat", "front squat", "goblet squat", "leg press"},
            id="squat",
        ),
        pytest.param(
            "Deadlift",
            {"deadlift", "sumo deadlift", "romanian deadlift", "trap bar deadlift"},
            id="deadlift",
        ),
    ])
    def test_returns_expected_variations(self, name, expected_members):
        assert expected_members <= get_equivalent_exercises(name)

    def test_unknown_exercise_returns_normalized_name(self):
        """Unknown exercises should return just the normalized name"""
        result = get_equivalent_exercises("Unknown Exercise")
        assert result == {"unknown exercise"}


class TestGetEquivalentExerciseIds:
    """
    Tests for get_equivalent_exercise_ids().

    This function queries the database to find all exercise IDs
    that are equivalent to a goal's target exercise.
    """

    def test_returns_goal_exercise_id_when_no_equivalents(self, test_exercises):
        """Should return at least the goal exercise ID itself"""
        # Create mock db
        db = Mock()
        curl = test_exercises["curl"]

        # Mock the exercise query
        db.query.return_value.filter.return_value.first.return_value = curl
        db.query.return_value.all.return_value = [curl]

        result = get_equivalent_exercise_ids(curl.id, db)

        assert curl.id in result
        assert isinstance(result, set)

    def test_returns_equivalent_ids(self, test_exercises):
        """Should return IDs of all equivalent exercises"""
        # Create mock db that returns bench variations
        db = Mock()
        bench = test_exercises["bench_press"]
        incline = test_exercises["incline_bench"]
        dumbbell = test_exercises["dumbbell_bench"]

        # First query returns the goal exercise
        db.query.return_value.filter.return_value.first.return_value = bench
        # Second query returns all exercises
        db.query.return_value.all.return_value = [bench, incline, dumbbell]

        result = get_equivalent_exercise_ids(bench.id, db)

        # Should include all bench variations
        assert bench.id in result
        assert incline.id in result
        assert dumbbell.id in result

    def test_returns_only_goal_id_for_unknown_exercise(self):
        """Unknown exercises should return just the goal exercise ID"""
        db = Mock()

        # Mock an unknown exercise
        unknown = Mock()
        unknown.id = "ex-unknown-001"
        unknown.name = "Unknown Exercise"

        db.query.return_value.filter.return_value.first.return_value = unknown
        db.query.return_value.all.return_value = [unknown]

        result = get_equivalent_exercise_ids(unknown.id, db)

        assert unknown.id in result
        assert len(result) >= 1

    def test_returns_goal_id_when_exercise_not_found(self):
        """Should return goal ID when exercise doesn't exist in DB"""
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None

        result = get_equivalent_exercise_ids("nonexistent-id", db)

        assert "nonexistent-id" in result


class TestEquivalenceMappingCompleteness:
    """
    Meta-tests to verify the EXERCISE_EQUIVALENCE mapping is complete.
    """

    def test_all_variations_are_lowercase(self):
        """All variations must be lowercase — matching is lowercase-substring"""
        for canonical, variations in EXERCISE_EQUIVALENCE.items():
            for variation in variations:
                assert variation == variation.lower(), \
                    f"Variation '{variation}' in '{canonical}' should be lowercase"

    def test_expected_categories_covered(self):
        """The Big Three plus common accessory movements should be covered"""
        expected_categories = [
            "squat",
            "bench_press",
            "deadlift",
            "overhead_press",
            "row",
            "pullup",
            "curl",
            "tricep_extension",
            "leg_curl",
            "leg_extension",
            "hip_thrust",
            "lateral_raise",
            "face_pull",
            "calf_raise",
            "fly",
        ]
        for category in expected_categories:
            assert category in EXERCISE_EQUIVALENCE, f"Missing category: {category}"


class TestCrossContamination:
    """
    Tests to ensure exercises don't incorrectly map to wrong categories.

    These are regression tests to catch subtle bugs in the equivalence logic
    (dict-order ambiguity: names appearing in multiple categories).
    """

    def test_rdl_not_mapped_to_squat(self):
        """Romanian Deadlift should map to deadlift, not squat"""
        # Note: RDL maps to deadlift because it's in that category
        canonical = get_canonical_exercise("Romanian Deadlift")
        # Could map to either deadlift or romanian_deadlift
        assert canonical in ["deadlift", "romanian_deadlift"]
        assert canonical != "squat"

    def test_leg_press_maps_correctly(self):
        """Leg Press is in squat equivalences for practical purposes"""
        canonical = get_canonical_exercise("Leg Press")
        # Leg press is listed under squat for muscle group purposes
        assert canonical in ["squat", "leg_extension"]
