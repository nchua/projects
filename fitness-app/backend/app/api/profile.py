"""
User profile API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User, UserProfile
from app.schemas.profile import ProfileUpdate, ProfileResponse

router = APIRouter()


@router.get("", response_model=ProfileResponse)
@router.get("/", response_model=ProfileResponse)
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get current user's profile

    Args:
        current_user: Currently authenticated user
        db: Database session

    Returns:
        User profile information

    Raises:
        HTTPException: If profile not found
    """
    # Get user profile
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )

    return ProfileResponse(
        id=profile.id,
        user_id=profile.user_id,
        email=current_user.email,
        username=current_user.username,
        age=profile.age,
        sex=profile.sex,
        bodyweight_lb=profile.bodyweight_lb,
        height_inches=profile.height_inches,
        training_experience=profile.training_experience.value,
        preferred_unit=profile.preferred_unit.value,
        e1rm_formula=profile.e1rm_formula.value,
        created_at=profile.created_at.isoformat(),
        updated_at=profile.updated_at.isoformat()
    )


@router.put("", response_model=ProfileResponse)
@router.put("/", response_model=ProfileResponse)
async def update_profile(
    profile_data: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update current user's profile

    Args:
        profile_data: Profile update data
        current_user: Currently authenticated user
        db: Database session

    Returns:
        Updated user profile information

    Raises:
        HTTPException: If profile not found
    """
    # Get user profile
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )

    # Update fields if provided
    update_data = profile_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(profile, field, value)

    db.commit()
    db.refresh(profile)

    return ProfileResponse(
        id=profile.id,
        user_id=profile.user_id,
        email=current_user.email,
        username=current_user.username,
        age=profile.age,
        sex=profile.sex,
        bodyweight_lb=profile.bodyweight_lb,
        height_inches=profile.height_inches,
        training_experience=profile.training_experience.value,
        preferred_unit=profile.preferred_unit.value,
        e1rm_formula=profile.e1rm_formula.value,
        created_at=profile.created_at.isoformat(),
        updated_at=profile.updated_at.isoformat()
    )
