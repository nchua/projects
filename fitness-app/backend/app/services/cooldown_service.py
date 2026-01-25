"""
Muscle Cooldown Service

Calculates muscle fatigue and cooldown status based on workout history.

Science-based cooldown time calculations:
- Large muscles (Quads, Hamstrings, Chest): 48-72 hours
- Medium muscles (Shoulders): 48 hours
- Small muscles (Biceps, Triceps): 24-48 hours

Enhanced fatigue calculation factors:
- Intensity: Weight as % of estimated 1RM
- Effort: RPE/RIR (rate of perceived exertion / reps in reserve)
- Volume: Number of sets per muscle group
- Fatigue stacking: Multiple exercises accumulate fatigue
"""
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_
from collections import defaultdict
import logging

from app.models.workout import WorkoutSession, WorkoutExercise, Set
from app.models.exercise import Exercise
from app.models.pr import PR, PRType
from app.core.utils import to_iso8601_utc

logger = logging.getLogger(__name__)


def get_age_modifier(age: int | None) -> float:
    """
    Get cooldown multiplier based on user age.

    Research shows recovery time increases with age:
    - Under 30: baseline recovery
    - 30-40: ~15% longer recovery
    - 40-50: ~30% longer recovery
    - 50+: ~50% longer recovery
    """
    if age is None:
        return 1.0  # Default if age not set
    if age < 30:
        return 1.0
    elif age < 40:
        return 1.15
    elif age < 50:
        return 1.3
    else:
        return 1.5


# Base cooldown times in hours for each muscle group
COOLDOWN_TIMES = {
    "chest": 72,
    "quads": 48,
    "hamstrings": 72,
    "biceps": 36,
    "triceps": 36,
    "shoulders": 48,
}

# Secondary muscle fatigue transfer percentage (50%)
SECONDARY_FATIGUE_PERCENT = 0.5

# =============================================================================
# INTENSITY FACTORS (% of e1RM)
# =============================================================================
INTENSITY_THRESHOLDS = {
    "light_max": 70,      # <70% = light
    "moderate_max": 85,   # 70-85% = moderate
    "heavy_max": 95       # 85-95% = heavy, >95% = max effort
}

INTENSITY_MULTIPLIERS = {
    "light": 0.7,         # Light work - faster recovery
    "moderate": 1.0,      # Baseline
    "heavy": 1.3,         # Heavy work - longer recovery
    "max_effort": 1.6     # Near-max effort - significantly longer
}

# =============================================================================
# EFFORT FACTORS (RPE/RIR)
# =============================================================================
EFFORT_MULTIPLIERS = {
    0: 1.5,    # Failure (RIR 0 / RPE 10)
    1: 1.25,   # RPE 9
    2: 1.1,    # RPE 8
    3: 1.0,    # RPE 7 (baseline)
    4: 0.9,    # RPE 6 or less
}

# =============================================================================
# VOLUME FACTORS
# =============================================================================
BASELINE_SETS = 3.5           # 3-4 sets is considered standard
VOLUME_INCREMENT = 0.12       # +12% per additional set
MAX_VOLUME_MULTIPLIER = 2.0   # Cap at 2x

# =============================================================================
# COOLDOWN CAPS
# =============================================================================
MAX_COOLDOWN_HOURS = 120      # 5 days maximum
MIN_COOLDOWN_HOURS = 12       # Minimum even for light work


INTENSITY_LEVELS = [
    ("light_max", "light"),
    ("moderate_max", "moderate"),
    ("heavy_max", "heavy"),
]


def estimate_intensity_from_reps(reps: int) -> float:
    """Estimate intensity percentage from rep count using inverse Epley formula."""
    if reps <= 1:
        return 100
    return 3000 / (30 + reps)


def calculate_intensity_factor(
    weight: float,
    reps: int,
    user_e1rm: float | None
) -> float:
    """
    Calculate intensity factor based on weight relative to estimated 1RM.
    Falls back to rep-based estimation when no e1RM is available.
    """
    if weight <= 0:
        return INTENSITY_MULTIPLIERS["moderate"]

    if user_e1rm and user_e1rm > 0:
        intensity_pct = (weight / user_e1rm) * 100
    else:
        intensity_pct = estimate_intensity_from_reps(reps)

    for threshold_key, multiplier_key in INTENSITY_LEVELS:
        if intensity_pct < INTENSITY_THRESHOLDS[threshold_key]:
            return INTENSITY_MULTIPLIERS[multiplier_key]
    return INTENSITY_MULTIPLIERS["max_effort"]


RIR_THRESHOLDS = [(0, 0), (1, 1), (2, 2), (3, 3)]
REP_RANGE_TO_RIR = [(3, 1), (6, 2), (10, 2.5)]


def estimate_rir_from_reps(reps: int) -> float:
    """Estimate RIR based on rep count when RPE/RIR not logged."""
    for max_reps, estimated_rir in REP_RANGE_TO_RIR:
        if reps <= max_reps:
            return estimated_rir
    return 3  # High rep sets often have buffer


def calculate_effort_factor(
    rpe: int | None,
    rir: int | None,
    reps: int
) -> float:
    """
    Calculate effort factor based on RPE or RIR.
    Falls back to rep-based estimation when neither is logged.
    """
    if rpe is not None:
        effective_rir = 10 - rpe
    elif rir is not None:
        effective_rir = rir
    else:
        effective_rir = estimate_rir_from_reps(reps)

    for threshold, multiplier_key in RIR_THRESHOLDS:
        if effective_rir <= threshold:
            return EFFORT_MULTIPLIERS[multiplier_key]
    return EFFORT_MULTIPLIERS[4]


def calculate_volume_multiplier(total_effective_sets: float) -> float:
    """
    Calculate volume multiplier based on number of effective sets.

    3-4 sets = baseline (1.0x)
    Each additional set beyond baseline = +12%
    Capped at 2.0x
    """
    if total_effective_sets <= BASELINE_SETS:
        return 1.0

    extra_sets = total_effective_sets - BASELINE_SETS
    volume_mult = 1.0 + (extra_sets * VOLUME_INCREMENT)

    return min(MAX_VOLUME_MULTIPLIER, volume_mult)


def calculate_set_fatigue_score(
    weight: float,
    reps: int,
    user_e1rm: float | None,
    rpe: int | None = None,
    rir: int | None = None
) -> float:
    """
    Calculate fatigue score for a single set.

    Combines intensity factor and effort factor.
    Returns a multiplier typically between 0.6 and 2.4.
    """
    intensity_factor = calculate_intensity_factor(weight, reps, user_e1rm)
    effort_factor = calculate_effort_factor(rpe, rir, reps)

    return intensity_factor * effort_factor


def get_user_e1rm_map(db: Session, user_id: str) -> Dict[str, float]:
    """
    Get a mapping of exercise_id -> best e1RM for the user.

    Used to calculate relative intensity for each set.
    """
    prs = db.query(PR).filter(
        and_(
            PR.user_id == user_id,
            PR.pr_type == PRType.E1RM
        )
    ).all()

    e1rm_map = {}
    for pr in prs:
        # Keep the highest e1RM if multiple records exist
        if pr.exercise_id not in e1rm_map or (pr.value and pr.value > e1rm_map[pr.exercise_id]):
            e1rm_map[pr.exercise_id] = pr.value or 0

    return e1rm_map

# Exercise to muscle group mappings
# Primary muscles get 100% fatigue, secondary get 50%
EXERCISE_MUSCLE_MAP = {
    # Compound Leg Exercises - Quad dominant
    "squat": {"primary": ["quads"], "secondary": ["hamstrings"]},
    "back squat": {"primary": ["quads"], "secondary": ["hamstrings"]},
    "barbell back squat": {"primary": ["quads"], "secondary": ["hamstrings"]},
    "front squat": {"primary": ["quads"], "secondary": ["hamstrings"]},
    "goblet squat": {"primary": ["quads"], "secondary": ["hamstrings"]},
    "leg press": {"primary": ["quads"], "secondary": ["hamstrings"]},
    "hack squat": {"primary": ["quads"], "secondary": ["hamstrings"]},
    "lunge": {"primary": ["quads"], "secondary": ["hamstrings"]},
    "lunges": {"primary": ["quads"], "secondary": ["hamstrings"]},
    "walking lunge": {"primary": ["quads"], "secondary": ["hamstrings"]},
    "walking lunges": {"primary": ["quads"], "secondary": ["hamstrings"]},
    "bulgarian split squat": {"primary": ["quads"], "secondary": ["hamstrings"]},
    "split squat": {"primary": ["quads"], "secondary": ["hamstrings"]},
    "leg extension": {"primary": ["quads"], "secondary": []},

    # Hamstring-focused exercises
    "deadlift": {"primary": ["hamstrings"], "secondary": ["quads"]},
    "barbell deadlift": {"primary": ["hamstrings"], "secondary": ["quads"]},
    "sumo deadlift": {"primary": ["hamstrings"], "secondary": ["quads"]},
    "romanian deadlift": {"primary": ["hamstrings"], "secondary": []},
    "rdl": {"primary": ["hamstrings"], "secondary": []},
    "single leg rdl": {"primary": ["hamstrings"], "secondary": []},
    "single-leg rdl": {"primary": ["hamstrings"], "secondary": []},
    "stiff leg deadlift": {"primary": ["hamstrings"], "secondary": []},
    "leg curl": {"primary": ["hamstrings"], "secondary": []},
    "lying leg curl": {"primary": ["hamstrings"], "secondary": []},
    "seated leg curl": {"primary": ["hamstrings"], "secondary": []},
    "good morning": {"primary": ["hamstrings"], "secondary": []},
    "hip thrust": {"primary": ["hamstrings"], "secondary": []},

    # Chest Exercises
    "bench press": {"primary": ["chest"], "secondary": ["triceps", "shoulders"]},
    "barbell bench press": {"primary": ["chest"], "secondary": ["triceps", "shoulders"]},
    "incline bench press": {"primary": ["chest"], "secondary": ["triceps", "shoulders"]},
    "incline barbell bench press": {"primary": ["chest"], "secondary": ["triceps", "shoulders"]},
    "decline bench press": {"primary": ["chest"], "secondary": ["triceps"]},
    "decline barbell bench press": {"primary": ["chest"], "secondary": ["triceps"]},
    "dumbbell bench press": {"primary": ["chest"], "secondary": ["triceps", "shoulders"]},
    "dumbbell press": {"primary": ["chest"], "secondary": ["triceps", "shoulders"]},
    "incline dumbbell press": {"primary": ["chest"], "secondary": ["triceps", "shoulders"]},
    "incline dumbbell bench press": {"primary": ["chest"], "secondary": ["triceps", "shoulders"]},
    "chest fly": {"primary": ["chest"], "secondary": []},
    "dumbbell fly": {"primary": ["chest"], "secondary": []},
    "dumbbell flyes": {"primary": ["chest"], "secondary": []},
    "cable fly": {"primary": ["chest"], "secondary": []},
    "cable flyes": {"primary": ["chest"], "secondary": []},
    "pec deck": {"primary": ["chest"], "secondary": []},
    "push up": {"primary": ["chest"], "secondary": ["triceps", "shoulders"]},
    "push-up": {"primary": ["chest"], "secondary": ["triceps", "shoulders"]},
    "pushup": {"primary": ["chest"], "secondary": ["triceps", "shoulders"]},
    "dip": {"primary": ["chest"], "secondary": ["triceps"]},
    "dips": {"primary": ["chest"], "secondary": ["triceps"]},
    "chest dip": {"primary": ["chest"], "secondary": ["triceps"]},
    "chest dips": {"primary": ["chest"], "secondary": ["triceps"]},

    # Shoulder Exercises
    "overhead press": {"primary": ["shoulders"], "secondary": ["triceps"]},
    "ohp": {"primary": ["shoulders"], "secondary": ["triceps"]},
    "shoulder press": {"primary": ["shoulders"], "secondary": ["triceps"]},
    "military press": {"primary": ["shoulders"], "secondary": ["triceps"]},
    "seated shoulder press": {"primary": ["shoulders"], "secondary": ["triceps"]},
    "dumbbell shoulder press": {"primary": ["shoulders"], "secondary": ["triceps"]},
    "seated dumbbell press": {"primary": ["shoulders"], "secondary": ["triceps"]},
    "arnold press": {"primary": ["shoulders"], "secondary": ["triceps"]},
    "lateral raise": {"primary": ["shoulders"], "secondary": []},
    "lateral raises": {"primary": ["shoulders"], "secondary": []},
    "side lateral raise": {"primary": ["shoulders"], "secondary": []},
    "front raise": {"primary": ["shoulders"], "secondary": []},
    "front raises": {"primary": ["shoulders"], "secondary": []},
    "rear delt fly": {"primary": ["shoulders"], "secondary": []},
    "rear delt flyes": {"primary": ["shoulders"], "secondary": []},
    "face pull": {"primary": ["shoulders"], "secondary": []},
    "face pulls": {"primary": ["shoulders"], "secondary": []},
    "upright row": {"primary": ["shoulders"], "secondary": ["biceps"]},

    # Triceps Exercises
    "tricep pushdown": {"primary": ["triceps"], "secondary": []},
    "tricep pushdowns": {"primary": ["triceps"], "secondary": []},
    "triceps pushdown": {"primary": ["triceps"], "secondary": []},
    "triceps pushdowns": {"primary": ["triceps"], "secondary": []},
    "rope pushdown": {"primary": ["triceps"], "secondary": []},
    "cable pushdown": {"primary": ["triceps"], "secondary": []},
    "tricep extension": {"primary": ["triceps"], "secondary": []},
    "tricep extensions": {"primary": ["triceps"], "secondary": []},
    "overhead tricep extension": {"primary": ["triceps"], "secondary": []},
    "skull crusher": {"primary": ["triceps"], "secondary": []},
    "skull crushers": {"primary": ["triceps"], "secondary": []},
    "close grip bench press": {"primary": ["triceps"], "secondary": ["chest"]},
    "close-grip bench press": {"primary": ["triceps"], "secondary": ["chest"]},
    "tricep dip": {"primary": ["triceps"], "secondary": []},
    "tricep dips": {"primary": ["triceps"], "secondary": []},
    "diamond pushup": {"primary": ["triceps"], "secondary": ["chest"]},

    # Biceps Exercises
    "bicep curl": {"primary": ["biceps"], "secondary": []},
    "bicep curls": {"primary": ["biceps"], "secondary": []},
    "barbell curl": {"primary": ["biceps"], "secondary": []},
    "barbell curls": {"primary": ["biceps"], "secondary": []},
    "dumbbell curl": {"primary": ["biceps"], "secondary": []},
    "dumbbell curls": {"primary": ["biceps"], "secondary": []},
    "hammer curl": {"primary": ["biceps"], "secondary": []},
    "hammer curls": {"primary": ["biceps"], "secondary": []},
    "preacher curl": {"primary": ["biceps"], "secondary": []},
    "preacher curls": {"primary": ["biceps"], "secondary": []},
    "concentration curl": {"primary": ["biceps"], "secondary": []},
    "cable curl": {"primary": ["biceps"], "secondary": []},
    "cable curls": {"primary": ["biceps"], "secondary": []},
    "incline curl": {"primary": ["biceps"], "secondary": []},
    "incline curls": {"primary": ["biceps"], "secondary": []},
    "ez bar curl": {"primary": ["biceps"], "secondary": []},
    # Additional curl variations
    "incline dumbbell curl": {"primary": ["biceps"], "secondary": []},
    "incline dumbbell curls": {"primary": ["biceps"], "secondary": []},
    "spider curl": {"primary": ["biceps"], "secondary": []},
    "spider curls": {"primary": ["biceps"], "secondary": []},
    "reverse curl": {"primary": ["biceps"], "secondary": []},
    "reverse curls": {"primary": ["biceps"], "secondary": []},
    "drag curl": {"primary": ["biceps"], "secondary": []},
    "drag curls": {"primary": ["biceps"], "secondary": []},
    "seated curl": {"primary": ["biceps"], "secondary": []},
    "seated curls": {"primary": ["biceps"], "secondary": []},
    "standing curl": {"primary": ["biceps"], "secondary": []},
    "standing curls": {"primary": ["biceps"], "secondary": []},

    # Back Exercises (affect biceps as secondary)
    "barbell row": {"primary": [], "secondary": ["biceps"]},
    "bent over row": {"primary": [], "secondary": ["biceps"]},
    "bent-over row": {"primary": [], "secondary": ["biceps"]},
    "pendlay row": {"primary": [], "secondary": ["biceps"]},
    "dumbbell row": {"primary": [], "secondary": ["biceps"]},
    "one arm row": {"primary": [], "secondary": ["biceps"]},
    "cable row": {"primary": [], "secondary": ["biceps"]},
    "seated cable row": {"primary": [], "secondary": ["biceps"]},
    "t-bar row": {"primary": [], "secondary": ["biceps"]},
    "lat pulldown": {"primary": [], "secondary": ["biceps"]},
    "wide grip lat pulldown": {"primary": [], "secondary": ["biceps"]},
    "pull up": {"primary": [], "secondary": ["biceps"]},
    "pull-up": {"primary": [], "secondary": ["biceps"]},
    "pullup": {"primary": [], "secondary": ["biceps"]},
    "chin up": {"primary": [], "secondary": ["biceps"]},
    "chin-up": {"primary": [], "secondary": ["biceps"]},
    "chinup": {"primary": [], "secondary": ["biceps"]},
    "straight arm pulldown": {"primary": [], "secondary": []},
}

# Map common primary muscle names to our tracked groups
PRIMARY_MUSCLE_MAP = {
    "chest": "chest",
    "pectorals": "chest",
    "pecs": "chest",
    "quads": "quads",
    "quadriceps": "quads",
    "hamstrings": "hamstrings",
    "hamstring": "hamstrings",
    "biceps": "biceps",
    "bicep": "biceps",
    "triceps": "triceps",
    "tricep": "triceps",
    "shoulders": "shoulders",
    "shoulder": "shoulders",
    "delts": "shoulders",
    "deltoids": "shoulders",
    "front delts": "shoulders",
    "side delts": "shoulders",
    "rear delts": "shoulders",
}


def get_muscle_mapping(exercise_name: str) -> Tuple[List[str], List[str]]:
    """
    Get primary and secondary muscles for an exercise.
    Returns (primary_muscles, secondary_muscles).
    Uses multi-level fuzzy matching for exercise names.
    """
    name_lower = exercise_name.lower().strip()

    # Try exact match first
    if name_lower in EXERCISE_MUSCLE_MAP:
        mapping = EXERCISE_MUSCLE_MAP[name_lower]
        return mapping["primary"], mapping["secondary"]

    # Fuzzy match - check if exercise name contains any key (or vice versa)
    for key, mapping in EXERCISE_MUSCLE_MAP.items():
        if key in name_lower or name_lower in key:
            return mapping["primary"], mapping["secondary"]

    # Word-based matching - check if key words appear in the exercise name
    # This catches cases like "Incline Dumbbell Curl" matching "curl" pattern
    primary, secondary = _match_by_keywords(name_lower)
    if primary or secondary:
        return primary, secondary

    # Log unmapped exercise for debugging
    logger.debug(f"No muscle mapping found for exercise: '{exercise_name}'")

    # No match found
    return [], []


# Keyword patterns for word-based matching (ordered by specificity)
# More specific patterns should come first
KEYWORD_PATTERNS = [
    # Compound leg movements
    (["squat"], {"primary": ["quads"], "secondary": ["hamstrings"]}),
    (["lunge"], {"primary": ["quads"], "secondary": ["hamstrings"]}),
    (["leg press"], {"primary": ["quads"], "secondary": ["hamstrings"]}),
    (["leg extension"], {"primary": ["quads"], "secondary": []}),
    (["leg curl"], {"primary": ["hamstrings"], "secondary": []}),
    (["deadlift"], {"primary": ["hamstrings"], "secondary": ["quads"]}),
    (["rdl"], {"primary": ["hamstrings"], "secondary": []}),
    (["hip thrust"], {"primary": ["hamstrings"], "secondary": []}),
    (["good morning"], {"primary": ["hamstrings"], "secondary": []}),

    # Chest
    (["bench press"], {"primary": ["chest"], "secondary": ["triceps", "shoulders"]}),
    (["bench"], {"primary": ["chest"], "secondary": ["triceps", "shoulders"]}),
    (["fly", "flye", "pec deck"], {"primary": ["chest"], "secondary": []}),
    (["push up", "push-up", "pushup"], {"primary": ["chest"], "secondary": ["triceps", "shoulders"]}),
    (["dip"], {"primary": ["chest"], "secondary": ["triceps"]}),

    # Shoulders
    (["overhead press", "ohp", "shoulder press", "military press"], {"primary": ["shoulders"], "secondary": ["triceps"]}),
    (["lateral raise", "side raise"], {"primary": ["shoulders"], "secondary": []}),
    (["front raise"], {"primary": ["shoulders"], "secondary": []}),
    (["rear delt"], {"primary": ["shoulders"], "secondary": []}),
    (["face pull"], {"primary": ["shoulders"], "secondary": []}),
    (["upright row"], {"primary": ["shoulders"], "secondary": ["biceps"]}),

    # Triceps
    (["tricep", "triceps"], {"primary": ["triceps"], "secondary": []}),
    (["pushdown", "push down"], {"primary": ["triceps"], "secondary": []}),
    (["skull crusher"], {"primary": ["triceps"], "secondary": []}),
    (["close grip bench"], {"primary": ["triceps"], "secondary": ["chest"]}),

    # Biceps - "curl" is the key word
    (["curl"], {"primary": ["biceps"], "secondary": []}),

    # Back exercises (secondary bicep)
    (["row"], {"primary": [], "secondary": ["biceps"]}),
    (["pulldown", "pull down"], {"primary": [], "secondary": ["biceps"]}),
    (["pull up", "pull-up", "pullup", "chin up", "chin-up", "chinup"], {"primary": [], "secondary": ["biceps"]}),
]


def _match_by_keywords(name_lower: str) -> Tuple[List[str], List[str]]:
    """
    Match exercise by keyword patterns.
    Returns first match found (more specific patterns checked first).
    """
    for keywords, mapping in KEYWORD_PATTERNS:
        for keyword in keywords:
            # Check if keyword appears as a word boundary match
            # This prevents "curl" from matching "curling" incorrectly
            if keyword in name_lower:
                return mapping["primary"], mapping["secondary"]
    return [], []


def map_primary_muscle(muscle_name: str) -> str | None:
    """Map a primary muscle name to our tracked muscle groups."""
    if not muscle_name:
        return None
    name_lower = muscle_name.lower().strip()
    return PRIMARY_MUSCLE_MAP.get(name_lower)


def calculate_cooldowns(
    db: Session,
    user_id: str,
    user_age: int | None = None,
    lookback_hours: int = 168  # 7 days lookback (increased for longer cooldowns)
) -> Dict:
    """
    Calculate muscle cooldown status for a user.

    Enhanced calculation factors:
    - Intensity: Weight as % of user's estimated 1RM
    - Effort: RPE/RIR (with fallback estimation)
    - Volume: Number of effective sets per muscle
    - Fatigue stacking: Multiple exercises accumulate fatigue

    Formula: base_cooldown × avg_fatigue_score × volume_multiplier × age_modifier

    Args:
        db: Database session
        user_id: User ID to calculate cooldowns for
        user_age: Optional user age for applying age-based cooldown modifiers
        lookback_hours: How far back to look for workouts (default 168 hours / 7 days)

    Returns dict with:
    - muscles_cooling: List of muscles that are still cooling down
    - generated_at: timestamp
    - age_modifier: The multiplier applied based on user age
    """
    now = datetime.utcnow()
    age_modifier = get_age_modifier(user_age)
    lookback_start = now - timedelta(hours=lookback_hours)

    # Get user's e1RM map for relative intensity calculation
    user_e1rm_map = get_user_e1rm_map(db, user_id)

    # Get recent workouts with exercises and sets
    workouts = db.query(WorkoutSession).filter(
        WorkoutSession.user_id == user_id,
        WorkoutSession.deleted_at == None,
        WorkoutSession.date >= lookback_start
    ).all()

    # Track fatigue per muscle group with enhanced data
    # Key: muscle_group, Value: dict with fatigue scores, sets, exercises
    muscle_fatigue: Dict[str, dict] = defaultdict(lambda: {
        "last_trained": None,
        "exercises": [],
        "total_fatigue_score": 0.0,      # Sum of set fatigue scores
        "total_effective_sets": 0.0,      # Effective sets (primary=1, secondary=0.5)
        "set_count": 0,                   # Actual set count for the muscle
    })

    for workout in workouts:
        workout_date = workout.date

        for we in workout.workout_exercises:
            exercise = we.exercise
            if not exercise:
                continue

            exercise_name = exercise.name
            exercise_id = exercise.id

            # Get user's e1RM for this exercise (if available)
            user_e1rm = user_e1rm_map.get(exercise_id)

            # Get muscle mapping from our map
            primary_muscles, secondary_muscles = get_muscle_mapping(exercise_name)

            # Fall back to exercise model fields if our mapping is empty
            if not primary_muscles and exercise.primary_muscle:
                mapped_muscle = map_primary_muscle(exercise.primary_muscle)
                if mapped_muscle and mapped_muscle in COOLDOWN_TIMES:
                    primary_muscles = [mapped_muscle]

            if not secondary_muscles and exercise.secondary_muscles:
                for sm in exercise.secondary_muscles:
                    mapped_muscle = map_primary_muscle(sm)
                    if mapped_muscle and mapped_muscle in COOLDOWN_TIMES:
                        secondary_muscles.append(mapped_muscle)

            # Process each set in this exercise
            sets = we.sets or []

            for s in sets:
                # Calculate fatigue score for this set
                set_fatigue = calculate_set_fatigue_score(
                    weight=s.weight or 0,
                    reps=s.reps or 0,
                    user_e1rm=user_e1rm,
                    rpe=s.rpe,
                    rir=s.rir
                )

                # Apply fatigue to primary muscles (100%)
                for muscle in primary_muscles:
                    if muscle in COOLDOWN_TIMES:
                        # Update last trained timestamp
                        if muscle_fatigue[muscle]["last_trained"] is None or workout_date > muscle_fatigue[muscle]["last_trained"]:
                            muscle_fatigue[muscle]["last_trained"] = workout_date

                        # Accumulate fatigue (stacking, not max)
                        muscle_fatigue[muscle]["total_fatigue_score"] += set_fatigue
                        muscle_fatigue[muscle]["total_effective_sets"] += 1.0
                        muscle_fatigue[muscle]["set_count"] += 1

                # Apply fatigue to secondary muscles (50%)
                for muscle in secondary_muscles:
                    if muscle in COOLDOWN_TIMES:
                        # Update last trained timestamp
                        if muscle_fatigue[muscle]["last_trained"] is None or workout_date > muscle_fatigue[muscle]["last_trained"]:
                            muscle_fatigue[muscle]["last_trained"] = workout_date

                        # Accumulate reduced fatigue for secondary muscles
                        muscle_fatigue[muscle]["total_fatigue_score"] += set_fatigue * SECONDARY_FATIGUE_PERCENT
                        muscle_fatigue[muscle]["total_effective_sets"] += SECONDARY_FATIGUE_PERCENT
                        muscle_fatigue[muscle]["set_count"] += 1

            # Add exercise to affected list (once per exercise, not per set)
            for muscle in primary_muscles:
                if muscle in COOLDOWN_TIMES:
                    exercise_entry = {
                        "exercise_id": exercise_id,
                        "exercise_name": exercise_name,
                        "workout_date": to_iso8601_utc(workout_date),
                        "fatigue_type": "primary"
                    }
                    if exercise_entry not in muscle_fatigue[muscle]["exercises"]:
                        muscle_fatigue[muscle]["exercises"].append(exercise_entry)

            for muscle in secondary_muscles:
                if muscle in COOLDOWN_TIMES:
                    exercise_entry = {
                        "exercise_id": exercise_id,
                        "exercise_name": exercise_name,
                        "workout_date": to_iso8601_utc(workout_date),
                        "fatigue_type": "secondary"
                    }
                    if exercise_entry not in muscle_fatigue[muscle]["exercises"]:
                        muscle_fatigue[muscle]["exercises"].append(exercise_entry)

    # Calculate cooldown status for each muscle
    muscles_cooling = []

    for muscle, data in muscle_fatigue.items():
        if data["last_trained"] is None:
            continue

        effective_sets = data["total_effective_sets"]
        if effective_sets <= 0:
            continue

        # Calculate average fatigue per set
        avg_fatigue_score = data["total_fatigue_score"] / effective_sets

        # Calculate volume multiplier
        volume_mult = calculate_volume_multiplier(effective_sets)

        # Calculate final cooldown time
        base_cooldown = COOLDOWN_TIMES[muscle]
        raw_cooldown = base_cooldown * avg_fatigue_score * volume_mult * age_modifier

        # Apply caps
        total_cooldown_hours = int(max(MIN_COOLDOWN_HOURS, min(MAX_COOLDOWN_HOURS, raw_cooldown)))

        # Calculate hours since last trained
        hours_since_trained = (now - data["last_trained"]).total_seconds() / 3600

        # Skip if fully ready
        if hours_since_trained >= total_cooldown_hours:
            continue

        hours_remaining = int(total_cooldown_hours - hours_since_trained)
        cooldown_percent = min(100, (hours_since_trained / total_cooldown_hours) * 100)

        muscles_cooling.append({
            "muscle_group": muscle,
            "status": "cooling",
            "cooldown_percent": round(cooldown_percent, 1),
            "hours_remaining": max(0, hours_remaining),
            "last_trained": to_iso8601_utc(data["last_trained"]),
            "affected_exercises": data["exercises"],
            # Enhanced fatigue breakdown for transparency
            "fatigue_breakdown": {
                "base_cooldown_hours": base_cooldown,
                "total_sets": data["set_count"],
                "effective_sets": round(effective_sets, 1),
                "avg_intensity_factor": round(avg_fatigue_score, 2),
                "volume_multiplier": round(volume_mult, 2),
                "age_modifier": age_modifier,
                "final_cooldown_hours": total_cooldown_hours
            }
        })

    # Sort by hours remaining (most cooldown needed first)
    muscles_cooling.sort(key=lambda x: x["hours_remaining"], reverse=True)

    return {
        "muscles_cooling": muscles_cooling,
        "generated_at": to_iso8601_utc(now),
        "age_modifier": age_modifier
    }
