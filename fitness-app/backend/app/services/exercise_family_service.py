"""
Exercise family service (ARISE v3 spec §4.2).

Thin DB layer over ``exercise_family_defs``: keeps the ``exercise_families``
table in sync with the committed dict, assigns ``exercises.family_id`` by
canonical/alias name, and answers the two questions the downstream engines
ask — "which families has this user logged, with which exercise ids?" and
"which family is this exercise?".
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.exercise import Exercise
from app.models.exercise_family import ExerciseFamily
from app.models.workout import Set, WorkoutExercise, WorkoutSession
from app.services.exercise_family_defs import (
    FAMILY_DEFS,
    family_for_name,
    resolve_family_assignments,
)


def ensure_families(db: Session, *, dry_run: bool = False, commit: bool = True) -> int:
    """Upsert every ``FAMILY_DEFS`` row into ``exercise_families``.

    Inserts missing families and refreshes changed attributes on existing
    ones; never deletes. Returns the number of rows inserted or updated (0
    on a no-op re-run). ``dry_run`` only counts; ``commit=False`` flushes so
    a caller can commit the change together with its audit row.
    """
    existing: Dict[str, ExerciseFamily] = {
        f.id: f for f in db.query(ExerciseFamily).all()
    }
    changed = 0
    for slug, defn in FAMILY_DEFS.items():
        row = existing.get(slug)
        if row is None:
            if not dry_run:
                db.add(ExerciseFamily(id=slug, **defn))
            changed += 1
            continue
        dirty = {key: value for key, value in defn.items() if getattr(row, key) != value}
        if dirty:
            if not dry_run:
                for key, value in dirty.items():
                    setattr(row, key, value)
            changed += 1
    if changed and not dry_run:
        db.commit() if commit else db.flush()
    return changed


def planned_family_updates(
    db: Session,
    *,
    include_custom: bool = True,
    dry_run: bool = False,
    rows: Optional[List[Exercise]] = None,
) -> List[Tuple[Exercise, str]]:
    """The ``(exercise, family)`` pairs :func:`assign_family_ids` would write.

    Seeded rows resolve by exact name and inherit through ``canonical_id``;
    custom rows (``include_custom=True``) are name-matched case-insensitively.
    Existing non-NULL assignments are only changed when the dict disagrees,
    and a NULL result never clears a value already set. In ``dry_run`` the
    families :func:`ensure_families` has not inserted yet still count as
    known, so the preview matches the apply. Pass ``rows`` to reuse a scan
    the caller already made.
    """
    if rows is None:
        query = db.query(Exercise)
        if not include_custom:
            query = query.filter(Exercise.is_custom == False)
        rows = query.all()

    known = {f.id for f in db.query(ExerciseFamily.id).all()}
    if dry_run:
        known |= set(FAMILY_DEFS)
    assignments = resolve_family_assignments(
        (ex.id, ex.name, ex.canonical_id) for ex in rows
    )
    return [
        (ex, fam)
        for ex in rows
        if (fam := assignments.get(ex.id)) is not None and fam in known and ex.family_id != fam
    ]


def apply_family_updates(
    db: Session, updates: List[Tuple[Exercise, str]], *, commit: bool = True
) -> int:
    """Write a plan from :func:`planned_family_updates`; returns the row count."""
    for ex, fam in updates:
        ex.family_id = fam
    if updates:
        db.commit() if commit else db.flush()
    return len(updates)


def assign_family_ids(
    db: Session, *, include_custom: bool = True, dry_run: bool = False, commit: bool = True
) -> int:
    """Set ``exercises.family_id`` from canonical / alias names.

    Plans with :func:`planned_family_updates` and writes with
    :func:`apply_family_updates`. Returns the number of rows updated (0 on a
    re-run); ``dry_run`` only counts, ``commit=False`` flushes so the caller
    can commit alongside its audit row.
    """
    updates = planned_family_updates(db, include_custom=include_custom, dry_run=dry_run)
    return len(updates) if dry_run else apply_family_updates(db, updates, commit=commit)


def families_for_user(db: Session, user_id: str) -> List[dict]:
    """Families the user has ever logged a set on, with their exercise ids.

    Returns one dict per family (sorted by display name)::

        {"family_id", "display_name", "is_big_three", "increment_lb",
         "standards_key", "primary_muscle", "exercise_ids"}

    ``exercise_ids`` is every exercise id in that family the user has logged
    at least one set on (non-deleted sessions). Families with no logged
    exercise are omitted. Consumers: W1 anchors, W2 weekly points, W3 context.
    """
    rows = (
        db.query(Exercise.family_id, Exercise.id)
        .join(WorkoutExercise, WorkoutExercise.exercise_id == Exercise.id)
        .join(WorkoutSession, WorkoutSession.id == WorkoutExercise.session_id)
        .join(Set, Set.workout_exercise_id == WorkoutExercise.id)
        .filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.deleted_at.is_(None),
            Exercise.family_id.isnot(None),
        )
        .distinct()
        .all()
    )
    if not rows:
        return []

    ids_by_family: Dict[str, set] = defaultdict(set)
    for family_id, exercise_id in rows:
        ids_by_family[family_id].add(exercise_id)

    families = (
        db.query(ExerciseFamily)
        .filter(ExerciseFamily.id.in_(list(ids_by_family)))
        .all()
    )
    result = [
        {
            "family_id": fam.id,
            "display_name": fam.display_name,
            "is_big_three": bool(fam.is_big_three),
            "increment_lb": float(fam.increment_lb),
            "standards_key": fam.standards_key,
            "primary_muscle": fam.primary_muscle,
            "exercise_ids": sorted(ids_by_family[fam.id]),
        }
        for fam in families
    ]
    result.sort(key=lambda d: d["display_name"])
    return result


def family_for_exercise(db: Session, exercise_id: str) -> Optional[str]:
    """Family slug for an exercise id, or None.

    Reads ``exercises.family_id`` first; when NULL (a custom row created
    before the backfill, or a seed row the migration missed) falls back to
    the canonical group and finally an exact name match. Read-only — it
    never writes the resolved value back.
    """
    exercise = db.query(Exercise).filter(Exercise.id == exercise_id).first()
    if exercise is None:
        return None
    if exercise.family_id:
        return exercise.family_id
    if exercise.canonical_id:
        sibling = (
            db.query(Exercise.family_id)
            .filter(
                Exercise.canonical_id == exercise.canonical_id,
                Exercise.family_id.isnot(None),
            )
            .first()
        )
        if sibling and sibling[0]:
            return sibling[0]
    return family_for_name(exercise.name)


__all__ = [
    "assign_family_ids",
    "ensure_families",
    "families_for_user",
    "family_for_exercise",
    "apply_family_updates",
    "family_for_name",
    "planned_family_updates",
]
