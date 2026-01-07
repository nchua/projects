"""
Muscle Cooldown Service

Calculates muscle fatigue and cooldown status based on workout history.

Science-based cooldown time calculations:
- Large muscles (Quads, Hamstrings, Chest): 48-72 hours
- Medium muscles (Shoulders): 48 hours
- Small muscles (Biceps, Triceps): 24-48 hours

Fatigue transfer for compound movements:
- Primary muscles: 100% fatigue
- Secondary muscles: 50% fatigue
"""
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from sqlalchemy.orm import Session
from collections import defaultdict

from app.models.workout import WorkoutSession, WorkoutExercise
from app.models.exercise import Exercise


# Cooldown times in hours for each muscle group
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
    Uses fuzzy matching for exercise names.
    """
    name_lower = exercise_name.lower().strip()

    # Try exact match first
    if name_lower in EXERCISE_MUSCLE_MAP:
        mapping = EXERCISE_MUSCLE_MAP[name_lower]
        return mapping["primary"], mapping["secondary"]

    # Fuzzy match - check if exercise name contains any key
    for key, mapping in EXERCISE_MUSCLE_MAP.items():
        if key in name_lower or name_lower in key:
            return mapping["primary"], mapping["secondary"]

    # No match found
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
    lookback_hours: int = 96  # 4 days lookback
) -> Dict:
    """
    Calculate muscle cooldown status for a user.

    Returns dict with:
    - muscles_cooling: List of muscles that are still cooling down
    - generated_at: timestamp
    """
    now = datetime.utcnow()
    lookback_start = now - timedelta(hours=lookback_hours)

    # Get recent workouts with exercises
    workouts = db.query(WorkoutSession).filter(
        WorkoutSession.user_id == user_id,
        WorkoutSession.deleted_at == None,
        WorkoutSession.date >= lookback_start
    ).all()

    # Track fatigue per muscle group
    # Key: muscle_group, Value: dict with last_trained, exercises, etc.
    muscle_fatigue: Dict[str, dict] = defaultdict(lambda: {
        "last_trained": None,
        "exercises": [],
        "total_cooldown_hours": 0,
    })

    for workout in workouts:
        workout_date = workout.date

        for we in workout.workout_exercises:
            exercise = we.exercise
            if not exercise:
                continue

            exercise_name = exercise.name

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

            # Apply fatigue to primary muscles (100%)
            for muscle in primary_muscles:
                if muscle in COOLDOWN_TIMES:
                    # Update last trained if this workout is more recent
                    if muscle_fatigue[muscle]["last_trained"] is None or workout_date > muscle_fatigue[muscle]["last_trained"]:
                        muscle_fatigue[muscle]["last_trained"] = workout_date
                        muscle_fatigue[muscle]["total_cooldown_hours"] = COOLDOWN_TIMES[muscle]

                    # Add exercise to affected list (avoid duplicates)
                    exercise_entry = {
                        "exercise_id": exercise.id,
                        "exercise_name": exercise_name,
                        "workout_date": workout_date.isoformat(),
                        "fatigue_type": "primary"
                    }
                    if exercise_entry not in muscle_fatigue[muscle]["exercises"]:
                        muscle_fatigue[muscle]["exercises"].append(exercise_entry)

            # Apply fatigue to secondary muscles (50%)
            for muscle in secondary_muscles:
                if muscle in COOLDOWN_TIMES:
                    secondary_fatigue = int(COOLDOWN_TIMES[muscle] * SECONDARY_FATIGUE_PERCENT)

                    # Update last trained if this workout is more recent
                    if muscle_fatigue[muscle]["last_trained"] is None or workout_date > muscle_fatigue[muscle]["last_trained"]:
                        muscle_fatigue[muscle]["last_trained"] = workout_date
                        # For secondary, use reduced fatigue time (but don't reduce existing primary fatigue)
                        muscle_fatigue[muscle]["total_cooldown_hours"] = max(
                            muscle_fatigue[muscle]["total_cooldown_hours"],
                            secondary_fatigue
                        )

                    # Add exercise to affected list (avoid duplicates)
                    exercise_entry = {
                        "exercise_id": exercise.id,
                        "exercise_name": exercise_name,
                        "workout_date": workout_date.isoformat(),
                        "fatigue_type": "secondary"
                    }
                    if exercise_entry not in muscle_fatigue[muscle]["exercises"]:
                        muscle_fatigue[muscle]["exercises"].append(exercise_entry)

    # Calculate cooldown status for each muscle
    muscles_cooling = []

    for muscle, data in muscle_fatigue.items():
        if data["last_trained"] is None:
            continue

        # Calculate hours since last trained
        hours_since_trained = (now - data["last_trained"]).total_seconds() / 3600
        cooldown_time = data["total_cooldown_hours"]

        # Skip if fully ready
        if hours_since_trained >= cooldown_time:
            continue

        hours_remaining = int(cooldown_time - hours_since_trained)
        cooldown_percent = min(100, (hours_since_trained / cooldown_time) * 100)

        muscles_cooling.append({
            "muscle_group": muscle,
            "status": "cooling",
            "cooldown_percent": round(cooldown_percent, 1),
            "hours_remaining": max(0, hours_remaining),
            "last_trained": data["last_trained"].isoformat(),
            "affected_exercises": data["exercises"]
        })

    # Sort by hours remaining (most cooldown needed first)
    muscles_cooling.sort(key=lambda x: x["hours_remaining"], reverse=True)

    return {
        "muscles_cooling": muscles_cooling,
        "generated_at": now.isoformat()
    }
