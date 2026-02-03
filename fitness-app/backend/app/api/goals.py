"""
Goals API endpoints - Strength PR goals CRUD
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.exercise import Exercise
from app.services.mission_service import (
    create_goal,
    get_user_goals,
    get_goal_by_id,
    update_goal,
    goal_to_response,
    goal_to_summary,
    GoalStatus,
    MAX_ACTIVE_GOALS
)
from app.schemas.mission import (
    GoalCreate,
    GoalUpdate,
    GoalResponse,
    GoalSummaryResponse,
    GoalsListResponse,
    GoalBatchCreate,
    GoalBatchCreateResponse,
    MAX_ACTIVE_GOALS as SCHEMA_MAX_GOALS
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
    # Check max goals limit
    active_goals = get_user_goals(db, current_user.id, include_inactive=False)
    if len(active_goals) >= MAX_ACTIVE_GOALS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {MAX_ACTIVE_GOALS} active goals allowed. Abandon or complete existing goals first."
        )

    # Verify exercise exists
    exercise = db.query(Exercise).filter(Exercise.id == goal_data.exercise_id).first()
    if not exercise:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Exercise not found"
        )

    # Create the goal
    goal = create_goal(
        db=db,
        user_id=current_user.id,
        exercise_id=goal_data.exercise_id,
        target_weight=goal_data.target_weight,
        weight_unit=goal_data.weight_unit,
        deadline=goal_data.deadline,
        target_reps=goal_data.target_reps,
        notes=goal_data.notes
    )

    db.commit()
    db.refresh(goal)

    # Reload with exercise relationship
    goal = get_goal_by_id(db, current_user.id, goal.id)

    return GoalResponse(**goal_to_response(goal))


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

    # Verify all exercises exist
    exercise_ids = [g.exercise_id for g in batch_data.goals]
    exercises = db.query(Exercise).filter(Exercise.id.in_(exercise_ids)).all()
    found_ids = {e.id for e in exercises}
    missing_ids = set(exercise_ids) - found_ids
    if missing_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Exercises not found: {', '.join(missing_ids)}"
        )

    # Create all goals
    created_goals = []
    for goal_data in batch_data.goals:
        goal = create_goal(
            db=db,
            user_id=current_user.id,
            exercise_id=goal_data.exercise_id,
            target_weight=goal_data.target_weight,
            weight_unit=goal_data.weight_unit,
            deadline=goal_data.deadline,
            target_reps=goal_data.target_reps,
            notes=goal_data.notes
        )
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
        goals=[GoalResponse(**goal_to_response(g)) for g in loaded_goals],
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
        goals=[GoalSummaryResponse(**goal_to_summary(g)) for g in goals],
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

    return GoalResponse(**goal_to_response(goal))


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

    return GoalResponse(**goal_to_response(updated_goal))


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
