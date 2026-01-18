"""
Friends API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func
from typing import List
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.friend import FriendRequest, Friendship, FriendRequestStatus
from app.models.workout import WorkoutSession
from app.models.progress import UserProgress
from app.models.pr import PR
from app.schemas.friend import (
    FriendRequestCreate,
    FriendRequestResponse,
    FriendRequestsResponse,
    FriendResponse,
    FriendProfileResponse,
    RecentWorkoutResponse
)

router = APIRouter()


def get_user_progress_info(db: Session, user_id: str) -> dict:
    """Get user's rank and level from progress table"""
    progress = db.query(UserProgress).filter(UserProgress.user_id == user_id).first()
    if progress:
        return {"rank": progress.rank.value if progress.rank else "E", "level": progress.level or 1}
    return {"rank": "E", "level": 1}


def build_friend_request_response(request: FriendRequest, db: Session) -> FriendRequestResponse:
    """Build FriendRequestResponse with user details"""
    sender_info = get_user_progress_info(db, request.sender_id)
    receiver_info = get_user_progress_info(db, request.receiver_id)

    return FriendRequestResponse(
        id=request.id,
        sender_id=request.sender_id,
        sender_username=request.sender.username if request.sender else None,
        sender_rank=sender_info["rank"],
        sender_level=sender_info["level"],
        receiver_id=request.receiver_id,
        receiver_username=request.receiver.username if request.receiver else None,
        receiver_rank=receiver_info["rank"],
        receiver_level=receiver_info["level"],
        status=request.status.value,
        created_at=request.created_at.isoformat()
    )


def build_friend_response(friendship: Friendship, db: Session) -> FriendResponse:
    """Build FriendResponse with friend details"""
    friend_info = get_user_progress_info(db, friendship.friend_id)

    # Get last workout time
    last_workout = db.query(WorkoutSession).filter(
        WorkoutSession.user_id == friendship.friend_id,
        WorkoutSession.deleted_at.is_(None)
    ).order_by(WorkoutSession.date.desc()).first()

    return FriendResponse(
        id=friendship.id,
        user_id=friendship.user_id,
        friend_id=friendship.friend_id,
        friend_username=friendship.friend.username if friendship.friend else None,
        friend_rank=friend_info["rank"],
        friend_level=friend_info["level"],
        created_at=friendship.created_at.isoformat(),
        last_workout_at=last_workout.date.isoformat() if last_workout else None
    )


@router.get("", response_model=List[FriendResponse])
@router.get("/", response_model=List[FriendResponse])
async def get_friends(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get list of current user's friends

    Returns:
        List of FriendResponse with friend details
    """
    friendships = db.query(Friendship).filter(
        Friendship.user_id == current_user.id
    ).all()

    return [build_friend_response(f, db) for f in friendships]


@router.get("/requests", response_model=FriendRequestsResponse)
async def get_friend_requests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get incoming and sent friend requests

    Returns:
        FriendRequestsResponse with incoming and sent lists
    """
    # Get incoming (pending) requests
    incoming = db.query(FriendRequest).filter(
        FriendRequest.receiver_id == current_user.id,
        FriendRequest.status == FriendRequestStatus.PENDING
    ).all()

    # Get sent (pending) requests
    sent = db.query(FriendRequest).filter(
        FriendRequest.sender_id == current_user.id,
        FriendRequest.status == FriendRequestStatus.PENDING
    ).all()

    return FriendRequestsResponse(
        incoming=[build_friend_request_response(r, db) for r in incoming],
        sent=[build_friend_request_response(r, db) for r in sent]
    )


@router.post("/request", response_model=FriendRequestResponse, status_code=status.HTTP_201_CREATED)
async def send_friend_request(
    request_data: FriendRequestCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Send a friend request to another user

    Args:
        request_data: Contains receiver_id

    Returns:
        Created FriendRequestResponse
    """
    # Can't add yourself
    if request_data.receiver_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot send friend request to yourself"
        )

    # Check receiver exists
    receiver = db.query(User).filter(User.id == request_data.receiver_id).first()
    if not receiver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Check if already friends
    existing_friendship = db.query(Friendship).filter(
        Friendship.user_id == current_user.id,
        Friendship.friend_id == request_data.receiver_id
    ).first()
    if existing_friendship:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already friends with this user"
        )

    # Check for existing pending request in either direction
    existing_request = db.query(FriendRequest).filter(
        or_(
            and_(
                FriendRequest.sender_id == current_user.id,
                FriendRequest.receiver_id == request_data.receiver_id
            ),
            and_(
                FriendRequest.sender_id == request_data.receiver_id,
                FriendRequest.receiver_id == current_user.id
            )
        ),
        FriendRequest.status == FriendRequestStatus.PENDING
    ).first()

    if existing_request:
        # If they already sent us a request, auto-accept it
        if existing_request.sender_id == request_data.receiver_id:
            existing_request.status = FriendRequestStatus.ACCEPTED

            # Create bidirectional friendship
            friendship1 = Friendship(user_id=current_user.id, friend_id=request_data.receiver_id)
            friendship2 = Friendship(user_id=request_data.receiver_id, friend_id=current_user.id)
            db.add(friendship1)
            db.add(friendship2)
            db.commit()
            db.refresh(existing_request)

            return build_friend_request_response(existing_request, db)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Friend request already pending"
            )

    # Create new request
    new_request = FriendRequest(
        sender_id=current_user.id,
        receiver_id=request_data.receiver_id
    )
    db.add(new_request)
    db.commit()
    db.refresh(new_request)

    return build_friend_request_response(new_request, db)


@router.post("/accept/{request_id}", response_model=FriendResponse)
async def accept_friend_request(
    request_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Accept an incoming friend request

    Args:
        request_id: ID of the friend request to accept

    Returns:
        Created FriendResponse
    """
    friend_request = db.query(FriendRequest).filter(
        FriendRequest.id == request_id,
        FriendRequest.receiver_id == current_user.id,
        FriendRequest.status == FriendRequestStatus.PENDING
    ).first()

    if not friend_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Friend request not found"
        )

    # Update request status
    friend_request.status = FriendRequestStatus.ACCEPTED

    # Create bidirectional friendship
    friendship1 = Friendship(user_id=current_user.id, friend_id=friend_request.sender_id)
    friendship2 = Friendship(user_id=friend_request.sender_id, friend_id=current_user.id)
    db.add(friendship1)
    db.add(friendship2)
    db.commit()
    db.refresh(friendship1)

    return build_friend_response(friendship1, db)


@router.post("/reject/{request_id}")
async def reject_friend_request(
    request_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Reject an incoming friend request

    Args:
        request_id: ID of the friend request to reject
    """
    friend_request = db.query(FriendRequest).filter(
        FriendRequest.id == request_id,
        FriendRequest.receiver_id == current_user.id,
        FriendRequest.status == FriendRequestStatus.PENDING
    ).first()

    if not friend_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Friend request not found"
        )

    friend_request.status = FriendRequestStatus.REJECTED
    db.commit()

    return {"message": "Friend request rejected"}


@router.delete("/cancel/{request_id}")
async def cancel_friend_request(
    request_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Cancel a sent friend request

    Args:
        request_id: ID of the friend request to cancel
    """
    friend_request = db.query(FriendRequest).filter(
        FriendRequest.id == request_id,
        FriendRequest.sender_id == current_user.id,
        FriendRequest.status == FriendRequestStatus.PENDING
    ).first()

    if not friend_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Friend request not found"
        )

    db.delete(friend_request)
    db.commit()

    return {"message": "Friend request cancelled"}


@router.delete("/{friend_id}")
async def remove_friend(
    friend_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Remove a friend (unfriend)

    Args:
        friend_id: User ID of the friend to remove
    """
    # Delete both directions of the friendship
    friendships = db.query(Friendship).filter(
        or_(
            and_(Friendship.user_id == current_user.id, Friendship.friend_id == friend_id),
            and_(Friendship.user_id == friend_id, Friendship.friend_id == current_user.id)
        )
    ).all()

    if not friendships:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Friendship not found"
        )

    for friendship in friendships:
        db.delete(friendship)
    db.commit()

    return {"message": "Friend removed"}


@router.get("/{friend_id}/profile", response_model=FriendProfileResponse)
async def get_friend_profile(
    friend_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a friend's profile with stats and recent activity

    Args:
        friend_id: User ID of the friend

    Returns:
        FriendProfileResponse with stats and recent workouts
    """
    # Verify they are friends
    friendship = db.query(Friendship).filter(
        Friendship.user_id == current_user.id,
        Friendship.friend_id == friend_id
    ).first()

    if not friendship:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not friends with this user"
        )

    # Get friend user
    friend = db.query(User).filter(User.id == friend_id).first()
    if not friend:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Get progress info
    progress_info = get_user_progress_info(db, friend_id)

    # Get total workouts
    total_workouts = db.query(func.count(WorkoutSession.id)).filter(
        WorkoutSession.user_id == friend_id,
        WorkoutSession.deleted_at.is_(None)
    ).scalar() or 0

    # Get total PRs
    total_prs = db.query(func.count(PR.id)).filter(
        PR.user_id == friend_id
    ).scalar() or 0

    # Get current streak from progress
    progress = db.query(UserProgress).filter(UserProgress.user_id == friend_id).first()
    current_streak = progress.current_streak if progress else 0

    # Get recent workouts (last 5)
    recent_workouts_query = db.query(WorkoutSession).filter(
        WorkoutSession.user_id == friend_id,
        WorkoutSession.deleted_at.is_(None)
    ).order_by(WorkoutSession.date.desc()).limit(5).all()

    recent_workouts = []
    for workout in recent_workouts_query:
        exercise_names = []
        for we in workout.exercises:
            if we.exercise:
                exercise_names.append(we.exercise.name)

        recent_workouts.append(RecentWorkoutResponse(
            id=workout.id,
            date=workout.date.isoformat(),
            exercise_count=len(workout.exercises),
            exercise_names=exercise_names,
            xp_earned=None  # Could track this if needed
        ))

    return FriendProfileResponse(
        user_id=friend_id,
        username=friend.username,
        rank=progress_info["rank"],
        level=progress_info["level"],
        total_workouts=total_workouts,
        current_streak=current_streak,
        total_prs=total_prs,
        recent_workouts=recent_workouts
    )
