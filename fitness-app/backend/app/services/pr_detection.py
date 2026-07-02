"""
PR (Personal Record) detection service
"""
from datetime import datetime, timezone
from typing import List

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.exercise import Exercise
from app.models.pr import PR, PRType
from app.models.workout import Set, WorkoutExercise

# Movements where a weight×reps 1RM (or a "more reps at this weight" rep PR) is
# not a meaningful strength signal, so logging them must NOT mint a PR. Two
# groups:
#   * Whole categories — pure cardio and sport are tracked by duration/distance,
#     never by a 1RM.
#   * Specific ballistic / plyometric / isometric movements that live in
#     otherwise-loadable categories (Legs/Core/Push). These are the explosive
#     throws & jumps, the sled, and timed holds the exercise-library expansion
#     (#21) added — you don't "rep-max" a Box Jump or a Wall Sit, and without
#     this guard a logged Box Jump would mint a bogus rep PR at the 0 lb bucket.
# Matched case-insensitively against EVERY name in an exercise's canonical group,
# so aliases (e.g. "Box Jumps", "Med Ball Slam") are covered too.
_NON_LOADABLE_CATEGORIES = frozenset({"cardio", "sport"})

_NON_LOADABLE_NAMES = frozenset({
    "medicine ball slam",
    "wall ball",
    "medicine ball chest pass",
    "medicine ball overhead throw",
    "box jump",
    "sled push",
    "wall sit",
    "hollow hold",
})


def _normalize_name(name: str) -> str:
    return (name or "").strip().lower()


def _canonical_group(db: Session, exercise_id: str):
    """Load an exercise and the (id, name) of every alias sharing its
    canonical_id, in at most two queries.

    Returns ``(exercise_or_None, rows)`` where ``rows`` is a list of
    ``(id, name)`` tuples for the whole canonical group (or just the exercise
    itself when it has no canonical_id). PR detection reuses one call for both
    the loadable check and the alias-id lookup so the hot path doesn't query the
    group twice.
    """
    exercise = db.query(Exercise).filter(Exercise.id == exercise_id).first()
    if not exercise:
        return None, []
    if not exercise.canonical_id:
        return exercise, [(exercise.id, exercise.name)]
    rows = db.query(Exercise.id, Exercise.name).filter(
        Exercise.canonical_id == exercise.canonical_id
    ).all()
    return exercise, [(r[0], r[1]) for r in rows] or [(exercise.id, exercise.name)]


def _is_loadable(exercise, group_rows) -> bool:
    """Loadable check over an already-loaded canonical group (see
    is_loadable_exercise for semantics)."""
    if exercise is None:
        return True
    if _normalize_name(exercise.category) in _NON_LOADABLE_CATEGORIES:
        return False
    # Check every alias in the canonical group, not just the logged row's name,
    # so logging an alias (e.g. "Box Jumps") is suppressed the same as the
    # canonical ("Box Jump").
    names = [name for _, name in group_rows] or [exercise.name]
    return not any(_normalize_name(n) in _NON_LOADABLE_NAMES for n in names)


def is_loadable_exercise(db: Session, exercise_id: str) -> bool:
    """Whether weight×reps PRs (e1RM / rep PR) are meaningful for this exercise.

    Returns False for pure cardio/sport categories and for ballistic,
    plyometric, or isometric-hold movements (slams, throws, jumps, sled, timed
    holds) where a 1RM or "more reps at a weight" carries no strength signal —
    preventing junk PRs like a "Jumping Jacks PR". Defaults to True (track) when
    the exercise can't be resolved.
    """
    exercise, group_rows = _canonical_group(db, exercise_id)
    return _is_loadable(exercise, group_rows)


def _weight_bucket(weight: float) -> float:
    """Round a weight to the nearest 2.5 lb — the smallest commercially
    plate-able increment. Using the same bucketing for both storage and
    lookup keys prevents float drift (e.g., 222.3 vs 222.6) from creating
    phantom duplicate rep PRs across workouts.
    """
    return round(weight * 2) / 2


def get_canonical_exercise_ids(db: Session, exercise_id: str) -> List[str]:
    """
    Get all exercise IDs that share the same canonical_id as the given exercise.
    This allows PR detection to consider all aliases of an exercise.
    """
    _, group_rows = _canonical_group(db, exercise_id)
    return [ex_id for ex_id, _ in group_rows] if group_rows else [exercise_id]


def detect_and_create_prs(
    db: Session,
    user_id: str,
    workout_exercise: WorkoutExercise,
    sets: List[Set]
) -> List[PR]:
    """
    Detect and create PRs for a workout exercise.
    Checks PRs across ALL exercises that share the same canonical_id,
    so "Back Squat" PRs are compared against "Squat" PRs.

    Args:
        db: Database session
        user_id: User ID
        workout_exercise: The workout exercise record
        sets: List of sets for this exercise

    Returns:
        List of newly created PRs
    """
    exercise_id = workout_exercise.exercise_id
    new_prs = []

    # Load the canonical group once and reuse it for both the loadable check and
    # the alias-id lookup below (avoids querying the group twice on the hot path).
    exercise, group_rows = _canonical_group(db, exercise_id)

    # Skip PR detection entirely for movements where a weight×reps 1RM is
    # meaningless — cardio/sport sessions, ballistic throws & jumps, sled work,
    # and timed holds. Otherwise logging e.g. Burpees or a Box Jump would mint a
    # bogus rep PR at the 0 lb bucket. See is_loadable_exercise.
    if not _is_loadable(exercise, group_rows):
        return new_prs

    # All exercise IDs that share the same canonical (e.g., Squat, Back Squat, BB Squat)
    related_exercise_ids = [ex_id for ex_id, _ in group_rows] or [exercise_id]

    # Get current best e1RM across ALL canonical aliases
    current_best_e1rm = db.query(func.max(PR.value)).filter(
        PR.user_id == user_id,
        PR.exercise_id.in_(related_exercise_ids),
        PR.pr_type == PRType.E1RM
    ).scalar() or 0

    # Get current rep PRs across ALL canonical aliases.
    # IMPORTANT: we bucket weights to the nearest 2.5 lb (see _weight_bucket)
    # both when STORING and LOOKING UP, so a 222.3 lb PR on day 1 and a 222.6
    # lb set on day 2 resolve to the same bucket and don't spuriously create a
    # duplicate PR. If two historical rows fall in the same bucket, we keep
    # the higher rep count — that's the one future sets must beat.
    existing_rep_prs = db.query(PR.weight, PR.reps).filter(
        PR.user_id == user_id,
        PR.exercise_id.in_(related_exercise_ids),
        PR.pr_type == PRType.REP_PR
    ).all()
    rep_pr_map: dict[float, int] = {}
    for weight, reps in existing_rep_prs:
        if weight is None:
            continue
        key = _weight_bucket(weight)
        if reps > rep_pr_map.get(key, 0):
            rep_pr_map[key] = reps

    # Check each set for PRs
    for set_obj in sets:
        achieved_at = datetime.now(timezone.utc)

        # Check for e1RM PR
        if set_obj.e1rm and set_obj.e1rm > current_best_e1rm:
            pr = PR(
                user_id=user_id,
                exercise_id=exercise_id,
                set_id=set_obj.id,
                pr_type=PRType.E1RM,
                value=set_obj.e1rm,
                achieved_at=achieved_at
            )
            db.add(pr)
            new_prs.append(pr)
            current_best_e1rm = set_obj.e1rm  # Update for subsequent sets

        # Check for rep PR at this weight bucket.
        weight = set_obj.weight
        reps = set_obj.reps
        weight_key = _weight_bucket(weight)

        current_best_reps = rep_pr_map.get(weight_key, 0)

        if reps > current_best_reps:
            pr = PR(
                user_id=user_id,
                exercise_id=exercise_id,
                set_id=set_obj.id,
                pr_type=PRType.REP_PR,
                weight=weight,
                reps=reps,
                achieved_at=achieved_at
            )
            db.add(pr)
            new_prs.append(pr)
            rep_pr_map[weight_key] = reps  # Update for subsequent sets

    return new_prs
