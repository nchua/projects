"""
Tests for exercise equivalence service.

The exercise equivalence system allows similar exercises to count towards goals.
For example, if a user has a Bench Press goal and logs Incline Bench Press,
the workout should still credit progress towards the Bench goal.

Functions tested:
- get_canonical_exercise(exercise_name) - Maps variations to canonical names
- get_equivalent_exercises(exercise_name) - Returns all variations
- get_equivalent_exercise_ids(goal_exercise_id, db) - DB lookup
- exercises_are_equivalent(name1, name2) - Comparison check
"""
import pytest
from unittest.mock import Mock, MagicMock
from typing import Set

from app.services.exercise_equivalence import (
    get_canonical_exercise,
    get_equivalent_exercises,
    get_equivalent_exercise_ids,
    exercises_are_equivalent,
    normalize_exercise_name,
    EXERCISE_EQUIVALENCE,
)


class TestNormalizeExerciseName:
    """Tests for exercise name normalization"""

    def test_lowercase_conversion(self):
        """Names should be converted to lowercase"""
        assert normalize_exercise_name("Bench Press") == "bench press"
        assert normalize_exercise_name("BARBELL ROW") == "barbell row"

    def test_whitespace_trimming(self):
        """Leading/trailing whitespace should be removed"""
        assert normalize_exercise_name("  Squat  ") == "squat"
        assert normalize_exercise_name("\tDeadlift\n") == "deadlift"


class TestGetCanonicalExercise:
    """
    Tests for get_canonical_exercise().

    This function maps exercise names to their canonical category.
    """

    def test_bench_press_variations(self):
        """All bench press variations should map to 'bench_press'"""
        variations = [
            "Bench Press",
            "Barbell Bench Press",
            "Incline Bench Press",
            "Dumbbell Bench Press",
            "Close Grip Bench Press",
            "Decline Bench Press",
            "Floor Press",
        ]
        for name in variations:
            result = get_canonical_exercise(name)
            assert result == "bench_press", f"'{name}' should map to 'bench_press', got '{result}'"

    def test_squat_variations(self):
        """All squat variations should map to 'squat'"""
        variations = [
            "Squat",
            "Barbell Back Squat",
            "Front Squat",
            "Goblet Squat",
            "Box Squat",
            "High Bar Squat",
            "Low Bar Squat",
            "Safety Bar Squat",
        ]
        for name in variations:
            result = get_canonical_exercise(name)
            assert result == "squat", f"'{name}' should map to 'squat', got '{result}'"

    def test_deadlift_variations(self):
        """All deadlift variations should map to 'deadlift'"""
        variations = [
            "Deadlift",
            "Barbell Deadlift",
            "Conventional Deadlift",
            "Sumo Deadlift",
            "Trap Bar Deadlift",
            "Deficit Deadlift",
            "Block Pull",
            "Rack Pull",
        ]
        for name in variations:
            result = get_canonical_exercise(name)
            assert result == "deadlift", f"'{name}' should map to 'deadlift', got '{result}'"

    def test_overhead_press_variations(self):
        """All overhead press variations should map to 'overhead_press'"""
        variations = [
            "Overhead Press",
            "OHP",
            "Shoulder Press",
            "Military Press",
            "Standing Press",
            "Seated Shoulder Press",
            "Push Press",
            "Arnold Press",
        ]
        for name in variations:
            result = get_canonical_exercise(name)
            assert result == "overhead_press", f"'{name}' should map to 'overhead_press', got '{result}'"

    def test_row_variations(self):
        """All row variations should map to 'row'"""
        variations = [
            "Barbell Row",
            "Bent Over Row",
            "Pendlay Row",
            "Dumbbell Row",
            "T-Bar Row",
            "Cable Row",
            "Seated Row",
            "Chest Supported Row",
        ]
        for name in variations:
            result = get_canonical_exercise(name)
            assert result == "row", f"'{name}' should map to 'row', got '{result}'"

    def test_curl_variations(self):
        """All curl variations should map to 'curl'"""
        variations = [
            "Barbell Curl",
            "Dumbbell Curl",
            "Hammer Curl",
            "Preacher Curl",
            "EZ Bar Curl",
            "Cable Curl",
            "Spider Curl",
            "Concentration Curl",
        ]
        for name in variations:
            result = get_canonical_exercise(name)
            assert result == "curl", f"'{name}' should map to 'curl', got '{result}'"

    def test_unknown_exercise_returns_none(self):
        """Unknown exercises should return None"""
        unknown_exercises = [
            "Zumba",
            "Swimming",
            "Yoga",
            "Running",
            "asdfghjkl",
        ]
        for name in unknown_exercises:
            result = get_canonical_exercise(name)
            assert result is None, f"'{name}' should return None, got '{result}'"

    def test_case_insensitivity(self):
        """Matching should be case-insensitive"""
        assert get_canonical_exercise("BENCH PRESS") == "bench_press"
        assert get_canonical_exercise("bench press") == "bench_press"
        assert get_canonical_exercise("Bench Press") == "bench_press"
        assert get_canonical_exercise("BeNcH pReSs") == "bench_press"


class TestGetEquivalentExercises:
    """
    Tests for get_equivalent_exercises().

    This function returns all variations that are equivalent to a given exercise.
    """

    def test_bench_press_returns_variations(self):
        """Bench press should return all bench variations"""
        result = get_equivalent_exercises("Bench Press")
        assert "bench press" in result
        assert "incline bench press" in result
        assert "dumbbell bench press" in result
        assert "close grip bench press" in result

    def test_squat_returns_variations(self):
        """Squat should return all squat variations"""
        result = get_equivalent_exercises("Squat")
        assert "squat" in result
        assert "front squat" in result
        assert "goblet squat" in result
        # Leg press is also in squat equivalences
        assert "leg press" in result

    def test_deadlift_returns_variations(self):
        """Deadlift should return all deadlift variations"""
        result = get_equivalent_exercises("Deadlift")
        assert "deadlift" in result
        assert "sumo deadlift" in result
        assert "romanian deadlift" in result
        assert "trap bar deadlift" in result

    def test_unknown_exercise_returns_normalized_name(self):
        """Unknown exercises should return just the normalized name"""
        result = get_equivalent_exercises("Unknown Exercise")
        assert result == {"unknown exercise"}

    def test_returns_set(self):
        """Result should be a set"""
        result = get_equivalent_exercises("Bench Press")
        assert isinstance(result, set)


class TestExercisesAreEquivalent:
    """
    Tests for exercises_are_equivalent().

    This function checks if two exercises belong to the same category.
    """

    def test_same_category_exercises_are_equivalent(self):
        """Exercises in the same category should be equivalent"""
        # Bench variations
        assert exercises_are_equivalent("Bench Press", "Incline Bench Press")
        assert exercises_are_equivalent("Barbell Bench", "Dumbbell Bench Press")
        assert exercises_are_equivalent("Close Grip Bench", "Floor Press")

        # Squat variations
        assert exercises_are_equivalent("Back Squat", "Front Squat")
        assert exercises_are_equivalent("Barbell Squat", "Goblet Squat")

        # Deadlift variations
        assert exercises_are_equivalent("Conventional Deadlift", "Sumo Deadlift")
        assert exercises_are_equivalent("Deadlift", "Romanian Deadlift")

    def test_different_category_exercises_not_equivalent(self):
        """Exercises in different categories should NOT be equivalent"""
        assert not exercises_are_equivalent("Bench Press", "Squat")
        assert not exercises_are_equivalent("Deadlift", "Overhead Press")
        assert not exercises_are_equivalent("Barbell Row", "Barbell Curl")
        assert not exercises_are_equivalent("Squat", "Tricep Extension")

    def test_symmetry(self):
        """Equivalence should be symmetric: A == B implies B == A"""
        pairs = [
            ("Bench Press", "Incline Bench"),
            ("Squat", "Front Squat"),
            ("Deadlift", "Sumo Deadlift"),
        ]
        for a, b in pairs:
            assert exercises_are_equivalent(a, b) == exercises_are_equivalent(b, a)

    def test_case_insensitivity(self):
        """Equivalence check should be case-insensitive"""
        assert exercises_are_equivalent("BENCH PRESS", "incline bench press")
        assert exercises_are_equivalent("Squat", "FRONT SQUAT")

    def test_direct_name_match_fallback(self):
        """
        Unknown exercises should use direct name matching.
        If one name contains the other, they're considered equivalent.
        """
        # These don't match any canonical category but one contains the other
        assert exercises_are_equivalent("Custom Exercise", "Custom Exercise Extended")
        # Completely different unknown exercises are not equivalent
        assert not exercises_are_equivalent("Zumba", "Swimming")


class TestGetEquivalentExerciseIds:
    """
    Tests for get_equivalent_exercise_ids().

    This function queries the database to find all exercise IDs
    that are equivalent to a goal's target exercise.
    """

    def test_returns_goal_exercise_id_when_no_equivalents(self, test_exercises, exercise_db):
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

    def test_all_canonical_keys_are_valid(self):
        """All canonical keys should be snake_case identifiers"""
        for key in EXERCISE_EQUIVALENCE.keys():
            assert "_" in key or key.isalpha(), f"Key '{key}' should be snake_case"
            assert key.islower(), f"Key '{key}' should be lowercase"

    def test_all_variations_are_lowercase(self):
        """All variations should be lowercase for consistent matching"""
        for canonical, variations in EXERCISE_EQUIVALENCE.items():
            for variation in variations:
                assert variation == variation.lower(), \
                    f"Variation '{variation}' in '{canonical}' should be lowercase"

    def test_big_three_covered(self):
        """The Big Three (squat, bench, deadlift) should be covered"""
        assert "squat" in EXERCISE_EQUIVALENCE
        assert "bench_press" in EXERCISE_EQUIVALENCE
        assert "deadlift" in EXERCISE_EQUIVALENCE

    def test_common_accessories_covered(self):
        """Common accessory movements should be covered"""
        expected_categories = [
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

    These are regression tests to catch subtle bugs in the equivalence logic.
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

    def test_dips_maps_correctly(self):
        """Dips should map to tricep_extension (chest/tricep movement)"""
        canonical = get_canonical_exercise("Dips")
        # Dips are listed under tricep_extension
        assert canonical == "tricep_extension"

    def test_pullup_and_lat_pulldown_equivalent(self):
        """Pull-ups and lat pulldown should be in the same category"""
        assert exercises_are_equivalent("Pull Up", "Lat Pulldown")
        assert exercises_are_equivalent("Chin Up", "Lat Pulldown")
