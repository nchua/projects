"""
Hunt name suggestions.

Derives a human-friendly session name when the user hasn't set one:

- Cardio/sport activities (WHOOP or Apple Watch imports) use the activity
  type: "TENNIS" -> "Tennis".
- Strength sessions use the primary muscles of the logged exercises:
  {Back, Biceps} -> "Back & Biceps Day", {Chest, Shoulders, Triceps} ->
  "Push Day", all-lower-body -> "Leg Day", upper+lower mix -> "Full Body Day".

The suggestion is computed at read time (never persisted), so it always
reflects the session's current exercises. The user-set ``name`` column wins
everywhere; clients fall back to the suggestion and finally the date.
"""

# Seeded primary_muscle values -> the coarse group shown in a name. Muscles
# missing from this map (e.g. "Full Body") keep their own label.
_DISPLAY_GROUP = {
    "chest": "Chest",
    "upper chest": "Chest",
    "lower chest": "Chest",
    "shoulders": "Shoulders",
    "front delts": "Shoulders",
    "side delts": "Shoulders",
    "rear delts": "Shoulders",
    "triceps": "Triceps",
    "back": "Back",
    "lats": "Back",
    "traps": "Back",
    "lower back": "Back",
    "biceps": "Biceps",
    "forearms": "Forearms",
    "quads": "Legs",
    "hamstrings": "Legs",
    "glutes": "Legs",
    "calves": "Legs",
    "adductors": "Legs",
    "legs": "Legs",
    "core": "Core",
    "abs": "Core",
    "lower abs": "Core",
    "obliques": "Core",
}

_PUSH = {"Chest", "Shoulders", "Triceps"}
_PULL = {"Back", "Biceps", "Forearms"}
_UPPER = _PUSH | _PULL


def _display_groups(primary_muscles: list[str]) -> list[str]:
    """Collapse raw primary muscles into ordered, deduplicated name groups."""
    groups: list[str] = []
    for muscle in primary_muscles:
        if not muscle:
            continue
        group = _DISPLAY_GROUP.get(muscle.strip().lower(), muscle.strip().title())
        if group not in groups:
            groups.append(group)
    return groups


def suggest_hunt_name(
    activity_type: str | None,
    primary_muscles: list[str] | None,
) -> str | None:
    """Suggested display name for a session, or None when nothing applies.

    Args:
        activity_type: Parsed cardio/sport activity type (WHOOP notes are
            uppercase like "TENNIS"; Apple Watch imports are already
            title-cased). Takes precedence when present.
        primary_muscles: Ordered primary muscles of the session's exercises
            (raw seeded values, e.g. ["Back", "Biceps", "Rear Delts"]).
    """
    if activity_type:
        cleaned = activity_type.strip()
        if cleaned:
            return cleaned.title() if not cleaned.istitle() else cleaned

    groups = _display_groups(primary_muscles or [])

    # Core and Full Body are usually accessories to the real focus — drop them
    # when anything more specific was trained.
    specific = [g for g in groups if g not in ("Core", "Full Body")]
    if not specific:
        if "Full Body" in groups:
            return "Full Body Day"
        if "Core" in groups:
            return "Core Day"
        return None

    if len(specific) == 1:
        only = specific[0]
        return "Leg Day" if only == "Legs" else f"{only} Day"

    if len(specific) == 2:
        return f"{specific[0]} & {specific[1]} Day"

    # 3+ groups: fall back to the classic split buckets.
    distinct = set(specific)
    if distinct <= _PUSH:
        return "Push Day"
    if distinct <= _PULL:
        return "Pull Day"
    if distinct <= _UPPER:
        return "Upper Body Day"
    return "Full Body Day"
