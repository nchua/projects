"""
PR (Personal Record) detection service
"""
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from typing import List, Tuple
from app.models.pr import PR, PRType
from app.models.workout import WorkoutExercise, Set
from app.models.exercise import Exercise


def get_canonical_exercise_ids(db: Session, exercise_id: str) -> List[str]:
    """
    Get all exercise IDs that share the same canonical_id as the given exercise.
    This allows PR detection to consider all aliases of an exercise.
    """
    exercise = db.query(Exercise).filter(Exercise.id == exercise_id).first()
    if not exercise or not exercise.canonical_id:
        return [exercise_id]

    # Find all exercises with the same canonical_id
    related = db.query(Exercise.id).filter(
        Exercise.canonical_id == exercise.canonical_id
    ).all()
    return [e.id for e in related] if related else [exercise_id]


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

    # Get all exercise IDs that share the same canonical (e.g., Squat, Back Squat, BB Squat)
    related_exercise_ids = get_canonical_exercise_ids(db, exercise_id)

    # Get current best e1RM across ALL canonical aliases
    current_best_e1rm = db.query(func.max(PR.value)).filter(
        PR.user_id == user_id,
        PR.exercise_id.in_(related_exercise_ids),
        PR.pr_type == PRType.E1RM
    ).scalar() or 0

    # Get current rep PRs across ALL canonical aliases (weight -> max reps)
    existing_rep_prs = db.query(PR.weight, PR.reps).filter(
        PR.user_id == user_id,
        PR.exercise_id.in_(related_exercise_ids),
        PR.pr_type == PRType.REP_PR
    ).all()
    rep_pr_map = {weight: reps for weight, reps in existing_rep_prs}

    # Check each set for PRs
    for set_obj in sets:
        achieved_at = datetime.utcnow()

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

        # Check for rep PR at this weight
        weight = set_obj.weight
        reps = set_obj.reps

        # Round weight to nearest 2.5 for comparison (handles floating point)
        weight_key = round(weight * 2) / 2

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


def check_first_time_exercise(
    db: Session,
    user_id: str,
    exercise_id: str
) -> bool:
    """
    Check if this is the user's first time performing an exercise.
    Considers all canonical aliases (e.g., "Squat" and "Back Squat" are the same).

    Args:
        db: Database session
        user_id: User ID
        exercise_id: Exercise ID

    Returns:
        True if this is the first time for this canonical exercise
    """
    related_exercise_ids = get_canonical_exercise_ids(db, exercise_id)
    existing = db.query(func.count(PR.id)).filter(
        PR.user_id == user_id,
        PR.exercise_id.in_(related_exercise_ids)
    ).scalar()
    return existing == 0
