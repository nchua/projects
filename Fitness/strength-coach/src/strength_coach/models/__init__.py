"""Pydantic models for strength coach data."""

from .exercises import (
    CanonicalExercise,
    ExerciseCategory,
    MuscleGroup,
    EXERCISE_REGISTRY,
    ALIAS_MAP,
    get_exercise,
    get_muscles_for_exercise,
    normalize_exercise,
)
from .workout import (
    ExercisePerformance,
    SetRecord,
    WeightUnit,
    WorkoutSession,
    WorkoutSessionInput,
)
from .bodyweight import (
    BodyWeightEntry,
    MeasurementMethod,
    TimeOfDay,
    UserProfile,
    DEFAULT_USER_PROFILE,
)
from .program import (
    ProgramBlock,
    TrainingGoal,
    TrainingWeek,
)
from .activity import (
    ActivitySource,
    CardioActivity,
    CardioWorkoutType,
    DailyActivityEntry,
    HeartRateZone,
)

__all__ = [
    # Exercises
    "CanonicalExercise",
    "ExerciseCategory",
    "MuscleGroup",
    "EXERCISE_REGISTRY",
    "ALIAS_MAP",
    "get_exercise",
    "get_muscles_for_exercise",
    "normalize_exercise",
    # Workout
    "ExercisePerformance",
    "SetRecord",
    "WeightUnit",
    "WorkoutSession",
    "WorkoutSessionInput",
    # Bodyweight
    "BodyWeightEntry",
    "MeasurementMethod",
    "TimeOfDay",
    "UserProfile",
    "DEFAULT_USER_PROFILE",
    # Program
    "ProgramBlock",
    "TrainingGoal",
    "TrainingWeek",
    # Activity
    "ActivitySource",
    "CardioActivity",
    "CardioWorkoutType",
    "DailyActivityEntry",
    "HeartRateZone",
]
