"""
Exercise Equivalence Service - Maps similar exercises that can count towards goals

When a user logs an exercise that's similar to their goal exercise,
it should still count as progress towards that goal.
"""
from typing import Set, Dict, List
from sqlalchemy.orm import Session

from app.models.exercise import Exercise


# Exercise equivalence mappings
# Key = canonical exercise keyword, Value = list of equivalent exercise keywords
EXERCISE_EQUIVALENCE: Dict[str, List[str]] = {
    # Bench Press variations
    "bench_press": [
        "bench press", "barbell bench press", "flat bench press",
        "incline bench press", "incline bench", "incline barbell bench",
        "decline bench press", "decline bench",
        "dumbbell bench press", "db bench press", "dumbbell press",
        "close grip bench press", "close grip bench", "cgbp",
        "pause bench", "pause bench press",
        "floor press",
    ],

    # Squat variations
    "squat": [
        "squat", "back squat", "barbell back squat", "barbell squat",
        "front squat", "barbell front squat",
        "high bar squat", "low bar squat",
        "goblet squat",
        "box squat",
        "pause squat",
        "safety bar squat", "ssb squat",
        "leg press",  # Partial equivalence for squat
    ],

    # Deadlift variations
    "deadlift": [
        "deadlift", "conventional deadlift", "barbell deadlift",
        "romanian deadlift", "rdl", "stiff leg deadlift",
        "sumo deadlift",
        "trap bar deadlift", "hex bar deadlift",
        "deficit deadlift",
        "block pull", "rack pull",
        "pause deadlift",
    ],

    # Overhead Press variations
    "overhead_press": [
        "overhead press", "ohp", "shoulder press", "military press",
        "standing press", "barbell press",
        "seated shoulder press", "seated ohp", "seated press",
        "dumbbell shoulder press", "db shoulder press", "dumbbell press",
        "push press",
        "behind the neck press", "btn press",
        "arnold press",
    ],

    # Row variations
    "row": [
        "row", "barbell row", "bent over row", "bent row", "bb row",
        "pendlay row",
        "dumbbell row", "db row", "one arm row", "single arm row",
        "t-bar row", "t bar row",
        "cable row", "seated cable row", "seated row",
        "chest supported row",
        "meadows row",
        "seal row",
    ],

    # Pull-up / Chin-up variations
    "pullup": [
        "pull up", "pullup", "pull-up",
        "chin up", "chinup", "chin-up",
        "weighted pull up", "weighted pullup", "weighted chin up",
        "neutral grip pull up", "neutral grip pullup",
        "lat pulldown", "pulldown", "lat pull down",  # Machine equivalent
    ],

    # Curl variations
    "curl": [
        "curl", "bicep curl", "barbell curl", "bb curl",
        "dumbbell curl", "db curl",
        "hammer curl", "hammer curls",
        "preacher curl",
        "incline curl", "incline dumbbell curl",
        "ez bar curl", "ez curl",
        "cable curl",
        "spider curl",
        "concentration curl",
    ],

    # Tricep variations
    "tricep_extension": [
        "tricep extension", "triceps extension", "tricep",
        "skull crusher", "skull crushers", "lying tricep extension",
        "tricep pushdown", "pushdown", "cable pushdown",
        "overhead tricep extension", "overhead extension",
        "dips",  # Also targets triceps
        "close grip bench press",  # Also targets triceps
        "jm press",
    ],

    # Leg curl variations
    "leg_curl": [
        "leg curl", "hamstring curl",
        "lying leg curl", "seated leg curl",
        "nordic curl", "nordic hamstring",
        "glute ham raise", "ghr",
    ],

    # Leg extension
    "leg_extension": [
        "leg extension", "quad extension",
        "leg press",  # Quad dominant
    ],

    # Hip thrust / Glute variations
    "hip_thrust": [
        "hip thrust", "barbell hip thrust",
        "glute bridge", "barbell glute bridge",
        "cable pull through",
    ],

    # Romanian Deadlift (also listed under deadlift, but has its own group)
    "romanian_deadlift": [
        "romanian deadlift", "rdl",
        "stiff leg deadlift", "sldl",
        "dumbbell romanian deadlift", "db rdl",
        "single leg rdl", "single leg romanian deadlift",
    ],

    # Lat Pulldown
    "lat_pulldown": [
        "lat pulldown", "pulldown", "lat pull down",
        "wide grip pulldown", "close grip pulldown",
        "neutral grip pulldown",
        "pull up", "pullup", "chin up", "chinup",  # Free weight equivalent
    ],

    # Lateral Raise
    "lateral_raise": [
        "lateral raise", "side raise", "side lateral raise",
        "dumbbell lateral raise", "db lateral raise",
        "cable lateral raise",
        "machine lateral raise",
    ],

    # Face Pull
    "face_pull": [
        "face pull", "face pulls",
        "cable face pull",
        "rear delt fly", "reverse fly",
    ],

    # Calf Raise
    "calf_raise": [
        "calf raise", "calf raises",
        "standing calf raise", "seated calf raise",
        "leg press calf raise",
        "donkey calf raise",
    ],

    # Fly / Pec Deck
    "fly": [
        "fly", "chest fly", "pec fly",
        "dumbbell fly", "db fly",
        "cable fly", "cable crossover",
        "pec deck", "machine fly",
        "incline fly", "incline dumbbell fly",
    ],
}


def normalize_exercise_name(name: str) -> str:
    """Normalize exercise name for matching"""
    return name.lower().strip()


def get_canonical_exercise(exercise_name: str) -> str | None:
    """
    Find the canonical exercise category for a given exercise name.

    Args:
        exercise_name: Name of the exercise

    Returns:
        Canonical exercise key (e.g., "bench_press") or None if no match
    """
    name_lower = normalize_exercise_name(exercise_name)

    for canonical, variations in EXERCISE_EQUIVALENCE.items():
        for variation in variations:
            if variation in name_lower or name_lower in variation:
                return canonical

    return None


def get_equivalent_exercises(exercise_name: str) -> Set[str]:
    """
    Get all exercise name variations that are equivalent to the given exercise.

    Args:
        exercise_name: Name of the exercise

    Returns:
        Set of equivalent exercise names (lowercase)
    """
    canonical = get_canonical_exercise(exercise_name)
    if canonical:
        return set(EXERCISE_EQUIVALENCE.get(canonical, []))
    return {normalize_exercise_name(exercise_name)}


def get_equivalent_exercise_ids(goal_exercise_id: str, db: Session) -> Set[str]:
    """
    Get all exercise IDs that count towards a goal exercise.

    This includes the goal exercise itself plus any equivalent variations.

    Args:
        goal_exercise_id: ID of the goal exercise
        db: Database session

    Returns:
        Set of exercise IDs that count towards the goal
    """
    # Get the goal exercise name
    goal_exercise = db.query(Exercise).filter(Exercise.id == goal_exercise_id).first()
    if not goal_exercise:
        return {goal_exercise_id}

    # Get equivalent exercise names
    equivalent_names = get_equivalent_exercises(goal_exercise.name)
    if not equivalent_names:
        return {goal_exercise_id}

    # Find all exercises that match the equivalent names
    equivalent_ids = {goal_exercise_id}

    # Query exercises with matching names
    all_exercises = db.query(Exercise).all()
    for exercise in all_exercises:
        name_lower = normalize_exercise_name(exercise.name)
        for equiv_name in equivalent_names:
            if equiv_name in name_lower or name_lower in equiv_name:
                equivalent_ids.add(exercise.id)
                break

    return equivalent_ids


def exercises_are_equivalent(exercise1_name: str, exercise2_name: str) -> bool:
    """
    Check if two exercises are equivalent (belong to same category).

    Args:
        exercise1_name: First exercise name
        exercise2_name: Second exercise name

    Returns:
        True if exercises are equivalent
    """
    canonical1 = get_canonical_exercise(exercise1_name)
    canonical2 = get_canonical_exercise(exercise2_name)

    if canonical1 and canonical2:
        return canonical1 == canonical2

    # Direct name match
    name1 = normalize_exercise_name(exercise1_name)
    name2 = normalize_exercise_name(exercise2_name)
    return name1 in name2 or name2 in name1
