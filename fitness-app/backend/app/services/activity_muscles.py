"""
Sport/cardio -> muscle-group proxy.

Cardio and sport sessions imported from Apple Watch (running, tennis, cycling…)
carry no exercises/sets, so we can't derive worked muscles the way we do for
strength training. This module maps an activity to a representative set of muscle
groups so those sessions can (a) show "muscles used" in the History log and
(b) feed the recovery/cooldown engine.

Muscle names are restricted to the groups the cooldown engine tracks
(``chest``, ``quads``, ``hamstrings``, ``biceps``, ``triceps``, ``shoulders``,
``glutes``, ``calves``) so the proxy is consistent between the muscles shown in
the log and the muscles that actually cool down. Names are returned title-cased
for display; the cooldown engine lower-cases them to match its vocabulary.

Note: core/back aren't tracked by the cooldown engine, so rotational/sport load
(e.g. golf, tennis trunk rotation) is approximated with the nearest tracked
groups or omitted rather than invented.
"""
from typing import Dict, List, Tuple

# activity name (lowercase) -> (primary muscles, secondary muscles), display-cased.
ACTIVITY_MUSCLE_PROXY: Dict[str, Tuple[List[str], List[str]]] = {
    "running": (["Quads", "Hamstrings", "Calves"], ["Glutes"]),
    "run": (["Quads", "Hamstrings", "Calves"], ["Glutes"]),
    "jog": (["Quads", "Hamstrings", "Calves"], ["Glutes"]),
    "jogging": (["Quads", "Hamstrings", "Calves"], ["Glutes"]),
    "walking": (["Quads", "Hamstrings"], ["Glutes", "Calves"]),
    "walk": (["Quads", "Hamstrings"], ["Glutes", "Calves"]),
    "hiking": (["Quads", "Hamstrings", "Calves"], ["Glutes"]),
    "cycling": (["Quads"], ["Hamstrings", "Glutes"]),
    "bike": (["Quads"], ["Hamstrings", "Glutes"]),
    "biking": (["Quads"], ["Hamstrings", "Glutes"]),
    "spinning": (["Quads"], ["Hamstrings", "Glutes"]),
    "tennis": (["Shoulders", "Quads"], ["Hamstrings", "Calves", "Triceps"]),
    "pickleball": (["Shoulders", "Quads"], ["Hamstrings", "Calves", "Triceps"]),
    "padel": (["Shoulders", "Quads"], ["Hamstrings", "Calves", "Triceps"]),
    "swimming": (["Shoulders"], ["Triceps", "Quads"]),
    "swim": (["Shoulders"], ["Triceps", "Quads"]),
    "rowing": (["Quads", "Hamstrings"], ["Shoulders", "Biceps"]),
    "row": (["Quads", "Hamstrings"], ["Shoulders", "Biceps"]),
    "jump rope": (["Calves"], ["Quads", "Hamstrings"]),
    "stair climber": (["Quads", "Glutes"], ["Calves", "Hamstrings"]),
    "elliptical": (["Quads", "Hamstrings"], ["Glutes", "Shoulders"]),
    "hiit": (["Quads", "Hamstrings", "Shoulders"], ["Glutes", "Chest"]),
    "basketball": (["Quads", "Hamstrings", "Calves"], ["Glutes"]),
    "soccer": (["Quads", "Hamstrings"], ["Calves", "Glutes"]),
    "golf": ([], []),
}


def get_activity_muscles(name: str) -> Tuple[List[str], List[str]]:
    """Resolve an activity/exercise name to (primary, secondary) muscle groups.

    Matching is exact first, then bidirectional substring (so "Trail Running"
    matches "running"), then first-word (so "Jump Rope Intervals" matches the
    "jump rope" entry). Returns ``([], [])`` for activities with no proxy
    (e.g. "Yoga"), which contribute no fatigue and show no muscle pills.

    Args:
        name: Activity type or linked exercise name, any case.

    Returns:
        ``(primary_muscles, secondary_muscles)`` as fresh lists of display-cased
        muscle names drawn from the cooldown engine's tracked groups.
    """
    if not name:
        return [], []

    normalized = name.lower().strip()

    if normalized in ACTIVITY_MUSCLE_PROXY:
        primary, secondary = ACTIVITY_MUSCLE_PROXY[normalized]
        return list(primary), list(secondary)

    for key, (primary, secondary) in ACTIVITY_MUSCLE_PROXY.items():
        if key in normalized or normalized in key:
            return list(primary), list(secondary)

    words = set(normalized.split())
    for key, (primary, secondary) in ACTIVITY_MUSCLE_PROXY.items():
        if key.split()[0] in words:
            return list(primary), list(secondary)

    return [], []
