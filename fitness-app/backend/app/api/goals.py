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
    GoalStatus
)
from app.schemas.mission import (
    GoalCreate,
    GoalUpdate,
    GoalResponse,
    GoalSummaryResponse,
    GoalsListResponse
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
    """
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
        List of goals with counts
    """
    goals = get_user_goals(db, current_user.id, include_inactive=include_inactive)

    active_count = sum(1 for g in goals if g.status == GoalStatus.ACTIVE.value)
    completed_count = sum(1 for g in goals if g.status == GoalStatus.COMPLETED.value)

    return GoalsListResponse(
        goals=[GoalSummaryResponse(**goal_to_summary(g)) for g in goals],
        active_count=active_count,
        completed_count=completed_count
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
