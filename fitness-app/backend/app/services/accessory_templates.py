"""
Accessory exercise templates for mission workout generation.

Each workout includes a primary lift (the goal exercise) plus 3-4 accessory
exercises for a complete ~45 minute training session.

Weight percentages are relative to the primary lift's prescribed weight.
"""
from typing import Dict, List, Any


# Accessory templates by muscle group (push/pull/legs)
# Each entry: exercise_name, sets, reps, weight_pct (% of primary lift weight)
ACCESSORY_TEMPLATES: Dict[str, List[Dict[str, Any]]] = {
    "push": [
        # Primary accessories (use % of main lift weight)
        {"exercise_name": "Incline Dumbbell Bench Press", "sets": 3, "reps": 8, "weight_pct": 0.35},
        {"exercise_name": "Cable Flyes", "sets": 3, "reps": 12, "weight_pct": 0.25},
        # Secondary accessories (lighter isolation work)
        {"exercise_name": "Tricep Pushdowns", "sets": 3, "reps": 10, "weight_pct": 0.25},
        {"exercise_name": "Lateral Raises", "sets": 3, "reps": 12, "weight_pct": 0.12},
    ],
    "pull": [
        # Primary accessories
        {"exercise_name": "Barbell Row", "sets": 3, "reps": 8, "weight_pct": 0.50},
        {"exercise_name": "Lat Pulldown", "sets": 3, "reps": 10, "weight_pct": 0.40},
        # Secondary accessories
        {"exercise_name": "Face Pulls", "sets": 3, "reps": 15, "weight_pct": 0.15},
        {"exercise_name": "Barbell Curl", "sets": 3, "reps": 10, "weight_pct": 0.25},
    ],
    "legs": [
        # Primary accessories
        {"exercise_name": "Romanian Deadlift", "sets": 3, "reps": 8, "weight_pct": 0.60},
        {"exercise_name": "Leg Press", "sets": 3, "reps": 10, "weight_pct": 1.50},  # Leg press is typically heavier
        # Secondary accessories
        {"exercise_name": "Leg Curl", "sets": 3, "reps": 12, "weight_pct": 0.30},
        {"exercise_name": "Standing Calf Raise", "sets": 4, "reps": 12, "weight_pct": 0.50},
    ],
}

# Volume day uses lighter weights and higher reps
VOLUME_ACCESSORY_TEMPLATES: Dict[str, List[Dict[str, Any]]] = {
    "push": [
        {"exercise_name": "Dumbbell Bench Press", "sets": 3, "reps": 12, "weight_pct": 0.30},
        {"exercise_name": "Cable Flyes", "sets": 3, "reps": 15, "weight_pct": 0.20},
        {"exercise_name": "Tricep Pushdowns", "sets": 3, "reps": 12, "weight_pct": 0.20},
    ],
    "pull": [
        {"exercise_name": "Dumbbell Row", "sets": 3, "reps": 12, "weight_pct": 0.30},
        {"exercise_name": "Lat Pulldown", "sets": 3, "reps": 12, "weight_pct": 0.35},
        {"exercise_name": "Barbell Curl", "sets": 3, "reps": 12, "weight_pct": 0.20},
    ],
    "legs": [
        {"exercise_name": "Leg Press", "sets": 3, "reps": 15, "weight_pct": 1.20},
        {"exercise_name": "Leg Extension", "sets": 3, "reps": 12, "weight_pct": 0.30},
        {"exercise_name": "Leg Curl", "sets": 3, "reps": 12, "weight_pct": 0.25},
    ],
}

# Map goal exercise patterns to muscle groups for accessory selection
# This handles cases where the goal exercise name doesn't match simple keywords
# Longer patterns are checked first to ensure specific matches take precedence
EXERCISE_TO_GROUP_MAP = {
    # Specific patterns (longer, more specific matches first)
    "leg press": "legs",
    "leg curl": "legs",
    "leg extension": "legs",
    "hip thrust": "legs",
    # Push exercises
    "bench": "push",
    "press": "push",  # General "press" after specific leg patterns
    "dip": "push",
    "fly": "push",
    "flye": "push",
    "pushup": "push",
    "push-up": "push",
    # Pull exercises
    "deadlift": "pull",
    "row": "pull",
    "pull": "pull",
    "pulldown": "pull",
    "curl": "pull",  # General "curl" - leg curl handled above
    "chin": "pull",
    # Legs exercises
    "squat": "legs",
    "lunge": "legs",
    "leg": "legs",
    "calf": "legs",
    "glute": "legs",
}


def get_accessory_group(exercise_name: str) -> str:
    """
    Determine which accessory template group to use based on exercise name.

    Returns 'push', 'pull', 'legs', or 'full_body' (no accessories).
    """
    name_lower = exercise_name.lower()

    # Check specific patterns first (longer matches)
    for pattern, group in sorted(EXERCISE_TO_GROUP_MAP.items(), key=lambda x: -len(x[0])):
        if pattern in name_lower:
            return group

    # Special cases
    if "overhead" in name_lower or "ohp" in name_lower or "military" in name_lower:
        return "push"

    return "full_body"


def get_accessories_for_group(
    muscle_group: str,
    is_volume_day: bool = False,
    limit: int = 4
) -> List[Dict[str, Any]]:
    """
    Get accessory exercises for a muscle group.

    Args:
        muscle_group: 'push', 'pull', or 'legs'
        is_volume_day: Use volume templates (lighter weight, higher reps)
        limit: Maximum number of accessories to return

    Returns:
        List of accessory template dicts
    """
    if muscle_group == "full_body" or muscle_group not in ACCESSORY_TEMPLATES:
        return []

    templates = VOLUME_ACCESSORY_TEMPLATES if is_volume_day else ACCESSORY_TEMPLATES
    return templates.get(muscle_group, [])[:limit]
