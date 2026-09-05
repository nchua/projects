"""
Goals API endpoints - Strength PR goals CRUD
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db

logger = logging.getLogger(__name__)
from app.core.dependencies import get_current_user
from app.models.exercise import Exercise
from app.models.user import User
from app.schemas.goal import (
    GoalBatchCreate,
    GoalBatchCreateResponse,
    GoalCreate,
    GoalPreviewResponse,
    GoalProgressResponse,
    GoalResponse,
    GoalsListResponse,
    GoalSummaryResponse,
    GoalUpdate,
)
from app.services.goal_service import (
    MAX_ACTIVE_GOALS,
    GoalStatus,
    create_objective,
    get_goal_by_id,
    get_goal_progress_data,
    get_user_goals,
    goal_to_response,
    goal_to_summary,
    preview_goal,
    update_goal,
)

router = APIRouter()


@router.post("", response_model=GoalResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=GoalResponse, status_code=status.HTTP_201_CREATED)
async def create_new_goal(
    goal_data: GoalCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new strength PR goal.

    Args:
        goal_data: Goal details (exercise_id, target_weight, deadline, etc.)

    Returns:
        Created goal with progress metrics

    Raises:
        400: If max goals (5) reached or exercise not found
    """
    logger.info(f"Creating goal for user {current_user.id}: exercise={goal_data.exercise_id}, "
                f"target={goal_data.target_weight} {goal_data.weight_unit} x {goal_data.target_reps}")

    # Check max goals limit
    active_goals = get_user_goals(db, current_user.id, include_inactive=False)
    logger.info(f"User has {len(active_goals)} active goals (max: {MAX_ACTIVE_GOALS})")

    if len(active_goals) >= MAX_ACTIVE_GOALS:
        logger.warning(f"User {current_user.id} at max goals limit")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {MAX_ACTIVE_GOALS} active goals allowed. Abandon or complete existing goals first."
        )

    # Create the objective (validates the exercise / run shape, resolves by=arc_end)
    try:
        goal = create_objective(db, current_user.id, goal_data)
    except ValueError as exc:
        logger.error(f"Objective rejected: {exc}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    db.commit()
    db.refresh(goal)
    logger.info(f"Goal created successfully: {goal.id}")

    # Reload with exercise relationship
    goal = get_goal_by_id(db, current_user.id, goal.id)

    if not goal:
        logger.error("Goal not found after creation - this should not happen!")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Goal creation failed - please try again"
        )

    logger.info(f"Goal verified after reload: {goal.id}, exercise={goal.exercise.name if goal.exercise else 'None'}")

    return GoalResponse(**goal_to_response(goal, db))


@router.post("/preview", response_model=GoalPreviewResponse)
async def preview_objective(
    goal_data: GoalCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Pace preview before saving (ARISE v3 §4.6): e1RM today, target e1RM,
    required lb/week vs the 6-week slope; AMBITIOUS when required > 2× slope."""
    try:
        return GoalPreviewResponse(**preview_goal(db, current_user.id, goal_data))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/batch", response_model=GoalBatchCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_goals_batch(
    batch_data: GoalBatchCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create multiple strength PR goals at once (for multi-goal wizard).

    Args:
        batch_data: List of goals to create (max 5 total)

    Returns:
        Created goals with progress metrics

    Raises:
        400: If total goals would exceed max (5)
    """
    # Check max goals limit
    active_goals = get_user_goals(db, current_user.id, include_inactive=False)
    slots_available = MAX_ACTIVE_GOALS - len(active_goals)

    if len(batch_data.goals) > slots_available:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Can only create {slots_available} more goals. You have {len(active_goals)} active goals."
        )

    # Verify all exercises exist (strength rows)
    exercise_ids = [g.exercise_id for g in batch_data.goals if g.exercise_id]
    exercises = db.query(Exercise).filter(Exercise.id.in_(exercise_ids)).all() if exercise_ids else []
    found_ids = {e.id for e in exercises}
    missing_ids = set(exercise_ids) - found_ids
    if missing_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Exercises not found: {', '.join(sorted(missing_ids))}"
        )

    # Create all goals
    created_goals = []
    for goal_data in batch_data.goals:
        try:
            goal = create_objective(db, current_user.id, goal_data)
        except ValueError as exc:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        created_goals.append(goal)

    db.commit()

    # Reload with exercise relationships
    loaded_goals = []
    for goal in created_goals:
        loaded_goal = get_goal_by_id(db, current_user.id, goal.id)
        loaded_goals.append(loaded_goal)

    # Get updated active count
    active_goals = get_user_goals(db, current_user.id, include_inactive=False)

    return GoalBatchCreateResponse(
        goals=[GoalResponse(**goal_to_response(g, db)) for g in loaded_goals],
        created_count=len(loaded_goals),
        active_count=len(active_goals)
    )


@router.get("", response_model=GoalsListResponse)
@router.get("/", response_model=GoalsListResponse)
async def list_goals(
    include_inactive: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all goals for the current user.

    Args:
        include_inactive: Include completed/abandoned goals (default: False)

    Returns:
        List of goals with counts and availability info
    """
    goals = get_user_goals(db, current_user.id, include_inactive=include_inactive)

    active_count = sum(1 for g in goals if g.status == GoalStatus.ACTIVE.value)
    completed_count = sum(1 for g in goals if g.status == GoalStatus.COMPLETED.value)

    return GoalsListResponse(
        goals=[GoalSummaryResponse(**goal_to_summary(g, db)) for g in goals],
        active_count=active_count,
        completed_count=completed_count,
        can_add_more=active_count < MAX_ACTIVE_GOALS,
        max_goals=MAX_ACTIVE_GOALS
    )


@router.get("/{goal_id}", response_model=GoalResponse)
async def get_goal(
    goal_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific goal with full details.

    Args:
        goal_id: ID of the goal to retrieve

    Returns:
        Goal with progress metrics
    """
    goal = get_goal_by_id(db, current_user.id, goal_id)

    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Goal not found"
        )

    return GoalResponse(**goal_to_response(goal, db))


@router.put("/{goal_id}", response_model=GoalResponse)
async def update_existing_goal(
    goal_id: str,
    goal_data: GoalUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update an existing goal.

    Args:
        goal_id: ID of the goal to update
        goal_data: Fields to update

    Returns:
        Updated goal
    """
    goal = get_goal_by_id(db, current_user.id, goal_id)

    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Goal not found"
        )

    # Validate status if being updated
    if goal_data.status and goal_data.status not in [s.value for s in GoalStatus]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {[s.value for s in GoalStatus]}"
        )

    updated_goal = update_goal(
        db=db,
        goal=goal,
        target_weight=goal_data.target_weight,
        target_reps=goal_data.target_reps,
        weight_unit=goal_data.weight_unit,
        deadline=goal_data.deadline,
        notes=goal_data.notes,
        status=goal_data.status
    )

    db.commit()

    # Reload with exercise relationship
    updated_goal = get_goal_by_id(db, current_user.id, goal_id)

    return GoalResponse(**goal_to_response(updated_goal, db))


@router.delete("/{goal_id}")
async def abandon_goal(
    goal_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Abandon a goal (soft delete).

    Args:
        goal_id: ID of the goal to abandon

    Returns:
        Success message
    """
    goal = get_goal_by_id(db, current_user.id, goal_id)

    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Goal not found"
        )

    if goal.status != GoalStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only active goals can be abandoned"
        )

    update_goal(db, goal, status=GoalStatus.ABANDONED.value)
    db.commit()

    return {"message": "Goal abandoned successfully"}


@router.get("/{goal_id}/progress", response_model=GoalProgressResponse)
async def get_goal_progress(
    goal_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get goal progress history with projected vs actual data for charting.

    Args:
        goal_id: ID of the goal

    Returns:
        Progress data with actual points, projected line, and status
    """
    goal = get_goal_by_id(db, current_user.id, goal_id)

    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Goal not found"
        )

    progress_data = get_goal_progress_data(db, goal)

    return GoalProgressResponse(**progress_data)
