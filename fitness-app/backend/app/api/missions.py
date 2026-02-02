"""
Missions API endpoints - Weekly AI coaching missions
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.mission_service import (
    get_or_create_current_mission,
    get_mission_by_id,
    accept_mission,
    decline_mission,
    get_mission_history,
    mission_to_response,
    MissionStatus
)
from app.schemas.mission import (
    CurrentMissionResponse,
    WeeklyMissionResponse,
    MissionAcceptResponse,
    MissionDeclineResponse,
    MissionHistoryResponse,
    GoalSummaryResponse,
    WeeklyMissionSummary,
    MissionWorkoutSummary
)

router = APIRouter()


@router.get("/current", response_model=CurrentMissionResponse)
async def get_current_mission(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get the current week's mission for the user.

    If no mission exists and it's Sunday/Monday, one will be generated
    based on the user's active goals.

    Returns:
        - has_active_goal: Whether user has any active goals
        - goal: Summary of the primary goal (if exists)
        - mission: Current week's mission (if exists)
        - needs_goal_setup: True if user should create a goal first
    """
    result = get_or_create_current_mission(db, current_user.id)
    db.commit()

    # Build response with proper schema objects
    goal_summary = None
    if result.get("goal"):
        goal_summary = GoalSummaryResponse(**result["goal"])

    mission_summary = None
    if result.get("mission"):
        m = result["mission"]
        mission_summary = WeeklyMissionSummary(
            id=m["id"],
            goal_exercise_name=m["goal_exercise_name"],
            goal_target_weight=m["goal_target_weight"],
            goal_weight_unit=m["goal_weight_unit"],
            status=m["status"],
            week_start=m["week_start"],
            week_end=m["week_end"],
            xp_reward=m["xp_reward"],
            workouts_completed=m["workouts_completed"],
            workouts_total=m["workouts_total"],
            days_remaining=m["days_remaining"],
            workouts=[MissionWorkoutSummary(**w) for w in m["workouts"]]
        )

    return CurrentMissionResponse(
        has_active_goal=result["has_active_goal"],
        goal=goal_summary,
        mission=mission_summary,
        needs_goal_setup=result["needs_goal_setup"]
    )


@router.get("/{mission_id}", response_model=WeeklyMissionResponse)
async def get_mission(
    mission_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get full details of a specific mission.

    Args:
        mission_id: ID of the mission to retrieve

    Returns:
        Full mission details with workouts and prescriptions
    """
    mission = get_mission_by_id(db, current_user.id, mission_id)

    if not mission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mission not found"
        )

    return WeeklyMissionResponse(**mission_to_response(mission))


@router.post("/{mission_id}/accept", response_model=MissionAcceptResponse)
async def accept_weekly_mission(
    mission_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Accept a weekly mission.

    Once accepted, daily quests will be replaced with mission objectives
    until the mission is completed or expires.

    Args:
        mission_id: ID of the mission to accept

    Returns:
        Accepted mission details
    """
    try:
        result = accept_mission(db, current_user.id, mission_id)
        db.commit()

        return MissionAcceptResponse(
            success=result["success"],
            mission=WeeklyMissionResponse(**result["mission"]),
            message=result["message"]
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{mission_id}/decline", response_model=MissionDeclineResponse)
async def decline_weekly_mission(
    mission_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Decline a weekly mission.

    If declined, daily quests will continue as normal.
    A new mission will be offered next week.

    Args:
        mission_id: ID of the mission to decline

    Returns:
        Success message
    """
    try:
        result = decline_mission(db, current_user.id, mission_id)
        db.commit()

        return MissionDeclineResponse(
            success=result["success"],
            message=result["message"]
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/history/list", response_model=MissionHistoryResponse)
async def get_missions_history(
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get history of past missions.

    Args:
        limit: Maximum number of missions to return (default: 10)

    Returns:
        List of past missions with completion stats
    """
    result = get_mission_history(db, current_user.id, limit=limit)

    mission_summaries = []
    for m in result["missions"]:
        mission_summaries.append(WeeklyMissionSummary(
            id=m["id"],
            goal_exercise_name=m["goal_exercise_name"],
            goal_target_weight=m["goal_target_weight"],
            goal_weight_unit=m["goal_weight_unit"],
            status=m["status"],
            week_start=m["week_start"],
            week_end=m["week_end"],
            xp_reward=m["xp_reward"],
            workouts_completed=m["workouts_completed"],
            workouts_total=m["workouts_total"],
            days_remaining=m["days_remaining"],
            workouts=[MissionWorkoutSummary(**w) for w in m["workouts"]]
        ))

    return MissionHistoryResponse(
        missions=mission_summaries,
        total_completed=result["total_completed"],
        total_xp_earned=result["total_xp_earned"]
    )
