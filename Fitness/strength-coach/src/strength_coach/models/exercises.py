"""Canonical exercise definitions and alias mapping."""

from enum import Enum
from pydantic import BaseModel


class MuscleGroup(str, Enum):
    """Primary and secondary muscle groups for exercises."""

    QUADS = "quads"
    HAMSTRINGS = "hamstrings"
    GLUTES = "glutes"
    CHEST = "chest"
    BACK = "back"
    LATS = "lats"
    SHOULDERS = "shoulders"
    BICEPS = "biceps"
    TRICEPS = "triceps"
    CORE = "core"
    FOREARMS = "forearms"
    CALVES = "calves"


class ExerciseCategory(str, Enum):
    """Exercise classification."""

    COMPOUND = "compound"
    ISOLATION = "isolation"
    CARDIO = "cardio"


class CanonicalExercise(BaseModel):
    """Master exercise definition with metadata."""

    id: str
    display_name: str
    aliases: list[str]
    primary_muscles: list[MuscleGroup]
    secondary_muscles: list[MuscleGroup] = []
    category: ExerciseCategory
    is_percentile_tracked: bool = False
    is_bodyweight: bool = False


# Canonical exercise registry
EXERCISE_REGISTRY: dict[str, CanonicalExercise] = {
    "squat": CanonicalExercise(
        id="squat",
        display_name="Barbell Back Squat",
        aliases=["back squat", "bb squat", "squats", "barbell squat"],
        primary_muscles=[MuscleGroup.QUADS, MuscleGroup.GLUTES],
        secondary_muscles=[MuscleGroup.HAMSTRINGS, MuscleGroup.CORE],
        category=ExerciseCategory.COMPOUND,
        is_percentile_tracked=True,
    ),
    "bench_press": CanonicalExercise(
        id="bench_press",
        display_name="Barbell Bench Press",
        aliases=["bench", "bb bench", "flat bench", "barbell bench", "bench press"],
        primary_muscles=[MuscleGroup.CHEST],
        secondary_muscles=[MuscleGroup.TRICEPS, MuscleGroup.SHOULDERS],
        category=ExerciseCategory.COMPOUND,
        is_percentile_tracked=True,
    ),
    "deadlift": CanonicalExercise(
        id="deadlift",
        display_name="Conventional Deadlift",
        aliases=["dl", "conventional deadlift", "deadlifts"],
        primary_muscles=[MuscleGroup.BACK, MuscleGroup.HAMSTRINGS, MuscleGroup.GLUTES],
        secondary_muscles=[MuscleGroup.FOREARMS, MuscleGroup.CORE],
        category=ExerciseCategory.COMPOUND,
        is_percentile_tracked=True,
    ),
    "overhead_press": CanonicalExercise(
        id="overhead_press",
        display_name="Overhead Press",
        aliases=["ohp", "press", "shoulder press", "military press", "standing press"],
        primary_muscles=[MuscleGroup.SHOULDERS],
        secondary_muscles=[MuscleGroup.TRICEPS, MuscleGroup.CORE],
        category=ExerciseCategory.COMPOUND,
        is_percentile_tracked=True,
    ),
    "pull_up": CanonicalExercise(
        id="pull_up",
        display_name="Pull-up",
        aliases=["pullup", "pullups", "pull-ups", "pull ups"],
        primary_muscles=[MuscleGroup.LATS, MuscleGroup.BACK],
        secondary_muscles=[MuscleGroup.BICEPS, MuscleGroup.FOREARMS],
        category=ExerciseCategory.COMPOUND,
        is_bodyweight=True,
    ),
    "chin_up": CanonicalExercise(
        id="chin_up",
        display_name="Chin-up",
        aliases=["chinup", "chinups", "chin-ups", "chin ups"],
        primary_muscles=[MuscleGroup.LATS, MuscleGroup.BICEPS],
        secondary_muscles=[MuscleGroup.BACK, MuscleGroup.FOREARMS],
        category=ExerciseCategory.COMPOUND,
        is_bodyweight=True,
    ),
    "barbell_row": CanonicalExercise(
        id="barbell_row",
        display_name="Barbell Row",
        aliases=["bb row", "bent over row", "pendlay row", "rows"],
        primary_muscles=[MuscleGroup.BACK, MuscleGroup.LATS],
        secondary_muscles=[MuscleGroup.BICEPS, MuscleGroup.FOREARMS],
        category=ExerciseCategory.COMPOUND,
    ),
    "front_squat": CanonicalExercise(
        id="front_squat",
        display_name="Front Squat",
        aliases=["fs", "front squats"],
        primary_muscles=[MuscleGroup.QUADS],
        secondary_muscles=[MuscleGroup.GLUTES, MuscleGroup.CORE],
        category=ExerciseCategory.COMPOUND,
    ),
    "romanian_deadlift": CanonicalExercise(
        id="romanian_deadlift",
        display_name="Romanian Deadlift",
        aliases=["rdl", "rdls", "romanian dl", "stiff leg deadlift"],
        primary_muscles=[MuscleGroup.HAMSTRINGS, MuscleGroup.GLUTES],
        secondary_muscles=[MuscleGroup.BACK],
        category=ExerciseCategory.COMPOUND,
    ),
    "sumo_deadlift": CanonicalExercise(
        id="sumo_deadlift",
        display_name="Sumo Deadlift",
        aliases=["sumo dl", "sumo"],
        primary_muscles=[MuscleGroup.GLUTES, MuscleGroup.QUADS, MuscleGroup.BACK],
        secondary_muscles=[MuscleGroup.HAMSTRINGS],
        category=ExerciseCategory.COMPOUND,
        is_percentile_tracked=True,
    ),
    "incline_bench": CanonicalExercise(
        id="incline_bench",
        display_name="Incline Bench Press",
        aliases=["incline press", "incline bb bench", "incline"],
        primary_muscles=[MuscleGroup.CHEST, MuscleGroup.SHOULDERS],
        secondary_muscles=[MuscleGroup.TRICEPS],
        category=ExerciseCategory.COMPOUND,
    ),
    "dumbbell_bench": CanonicalExercise(
        id="dumbbell_bench",
        display_name="Dumbbell Bench Press",
        aliases=["db bench", "dumbbell press", "db press"],
        primary_muscles=[MuscleGroup.CHEST],
        secondary_muscles=[MuscleGroup.TRICEPS, MuscleGroup.SHOULDERS],
        category=ExerciseCategory.COMPOUND,
    ),
    "dip": CanonicalExercise(
        id="dip",
        display_name="Dip",
        aliases=["dips", "chest dip", "tricep dip"],
        primary_muscles=[MuscleGroup.CHEST, MuscleGroup.TRICEPS],
        secondary_muscles=[MuscleGroup.SHOULDERS],
        category=ExerciseCategory.COMPOUND,
        is_bodyweight=True,
    ),
    "barbell_curl": CanonicalExercise(
        id="barbell_curl",
        display_name="Barbell Curl",
        aliases=["bb curl", "curls", "bicep curl", "standing curl"],
        primary_muscles=[MuscleGroup.BICEPS],
        secondary_muscles=[MuscleGroup.FOREARMS],
        category=ExerciseCategory.ISOLATION,
    ),
    "dumbbell_curl": CanonicalExercise(
        id="dumbbell_curl",
        display_name="Dumbbell Curl",
        aliases=["db curl", "db curls"],
        primary_muscles=[MuscleGroup.BICEPS],
        secondary_muscles=[MuscleGroup.FOREARMS],
        category=ExerciseCategory.ISOLATION,
    ),
    "hammer_curl": CanonicalExercise(
        id="hammer_curl",
        display_name="Hammer Curl",
        aliases=["hammers", "hammer curls"],
        primary_muscles=[MuscleGroup.BICEPS],
        secondary_muscles=[MuscleGroup.FOREARMS],
        category=ExerciseCategory.ISOLATION,
    ),
    "tricep_pushdown": CanonicalExercise(
        id="tricep_pushdown",
        display_name="Tricep Pushdown",
        aliases=["pushdown", "cable pushdown", "rope pushdown"],
        primary_muscles=[MuscleGroup.TRICEPS],
        secondary_muscles=[],
        category=ExerciseCategory.ISOLATION,
    ),
    "skull_crusher": CanonicalExercise(
        id="skull_crusher",
        display_name="Skull Crusher",
        aliases=["skullcrushers", "lying tricep extension", "ez bar skull crusher"],
        primary_muscles=[MuscleGroup.TRICEPS],
        secondary_muscles=[],
        category=ExerciseCategory.ISOLATION,
    ),
    "lateral_raise": CanonicalExercise(
        id="lateral_raise",
        display_name="Lateral Raise",
        aliases=["side raise", "lat raise", "db lateral raise"],
        primary_muscles=[MuscleGroup.SHOULDERS],
        secondary_muscles=[],
        category=ExerciseCategory.ISOLATION,
    ),
    "face_pull": CanonicalExercise(
        id="face_pull",
        display_name="Face Pull",
        aliases=["face pulls", "cable face pull"],
        primary_muscles=[MuscleGroup.SHOULDERS, MuscleGroup.BACK],
        secondary_muscles=[],
        category=ExerciseCategory.ISOLATION,
    ),
    "leg_press": CanonicalExercise(
        id="leg_press",
        display_name="Leg Press",
        aliases=["lp", "machine leg press"],
        primary_muscles=[MuscleGroup.QUADS, MuscleGroup.GLUTES],
        secondary_muscles=[MuscleGroup.HAMSTRINGS],
        category=ExerciseCategory.COMPOUND,
    ),
    "leg_curl": CanonicalExercise(
        id="leg_curl",
        display_name="Leg Curl",
        aliases=["lying leg curl", "seated leg curl", "hamstring curl"],
        primary_muscles=[MuscleGroup.HAMSTRINGS],
        secondary_muscles=[],
        category=ExerciseCategory.ISOLATION,
    ),
    "leg_extension": CanonicalExercise(
        id="leg_extension",
        display_name="Leg Extension",
        aliases=["quad extension", "knee extension"],
        primary_muscles=[MuscleGroup.QUADS],
        secondary_muscles=[],
        category=ExerciseCategory.ISOLATION,
    ),
    "calf_raise": CanonicalExercise(
        id="calf_raise",
        display_name="Calf Raise",
        aliases=["standing calf raise", "seated calf raise", "calf raises"],
        primary_muscles=[MuscleGroup.CALVES],
        secondary_muscles=[],
        category=ExerciseCategory.ISOLATION,
    ),
    "lat_pulldown": CanonicalExercise(
        id="lat_pulldown",
        display_name="Lat Pulldown",
        aliases=["pulldown", "cable pulldown", "wide grip pulldown"],
        primary_muscles=[MuscleGroup.LATS],
        secondary_muscles=[MuscleGroup.BICEPS, MuscleGroup.BACK],
        category=ExerciseCategory.COMPOUND,
    ),
    "cable_row": CanonicalExercise(
        id="cable_row",
        display_name="Cable Row",
        aliases=["seated cable row", "low row", "seated row"],
        primary_muscles=[MuscleGroup.BACK, MuscleGroup.LATS],
        secondary_muscles=[MuscleGroup.BICEPS],
        category=ExerciseCategory.COMPOUND,
    ),
}

# Build alias map from registry
ALIAS_MAP: dict[str, str] = {}
for exercise_id, exercise in EXERCISE_REGISTRY.items():
    ALIAS_MAP[exercise_id] = exercise_id
    ALIAS_MAP[exercise.display_name.lower()] = exercise_id
    for alias in exercise.aliases:
        ALIAS_MAP[alias.lower()] = exercise_id


def normalize_exercise(name: str) -> str:
    """
    Normalize an exercise name to its canonical ID.

    Returns the canonical ID if found, otherwise returns the input
    lowercased and stripped.
    """
    normalized = name.lower().strip()
    return ALIAS_MAP.get(normalized, normalized)


def get_exercise(name: str) -> CanonicalExercise | None:
    """
    Get the CanonicalExercise for a given name or alias.

    Returns None if not found in registry.
    """
    canonical_id = normalize_exercise(name)
    return EXERCISE_REGISTRY.get(canonical_id)


def get_muscles_for_exercise(name: str) -> tuple[list[MuscleGroup], list[MuscleGroup]]:
    """
    Get primary and secondary muscles for an exercise.

    Returns empty lists if exercise not found.
    """
    exercise = get_exercise(name)
    if exercise:
        return exercise.primary_muscles, exercise.secondary_muscles
    return [], []
