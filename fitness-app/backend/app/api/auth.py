"""
Authentication API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token, verify_token
from app.core.utils import to_iso8601_utc
from app.models.user import User, UserProfile
from app.schemas.auth import UserRegister, UserLogin, Token, TokenRefresh, RegisterResponse, UserResponse

router = APIRouter()


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserRegister, db: Session = Depends(get_db)):
    """
    Register a new user account

    Args:
        user_data: User registration data (email, password)
        db: Database session

    Returns:
        Success message and user information

    Raises:
        HTTPException: If email already exists or validation fails
    """
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Hash password
    password_hash = hash_password(user_data.password)

    # Create new user
    new_user = User(
        email=user_data.email,
        password_hash=password_hash
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Create default user profile
    default_profile = UserProfile(user_id=new_user.id)
    db.add(default_profile)
    db.commit()

    # Prepare response
    user_response = UserResponse(
        id=new_user.id,
        email=new_user.email,
        created_at=to_iso8601_utc(new_user.created_at)
    )

    return RegisterResponse(
        message="User registered successfully",
        user=user_response
    )


@router.post("/login", response_model=Token)
async def login(user_data: UserLogin, db: Session = Depends(get_db)):
    """
    Authenticate user and return JWT tokens

    Args:
        user_data: User login credentials (email, password)
        db: Database session

    Returns:
        Access token and refresh token

    Raises:
        HTTPException: If credentials are invalid
    """
    # Find user by email
    user = db.query(User).filter(User.email == user_data.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify password
    if not verify_password(user_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create tokens
    access_token = create_access_token(data={"sub": user.id})
    refresh_token = create_refresh_token(data={"sub": user.id})

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(token_data: TokenRefresh, db: Session = Depends(get_db)):
    """
    Refresh access token using refresh token

    Args:
        token_data: Refresh token
        db: Database session

    Returns:
        New access token and refresh token

    Raises:
        HTTPException: If refresh token is invalid or expired
    """
    # Verify refresh token
    payload = verify_token(token_data.refresh_token, token_type="refresh")
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user_id from token
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify user still exists
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create new tokens
    access_token = create_access_token(data={"sub": user.id})
    new_refresh_token = create_refresh_token(data={"sub": user.id})

    return Token(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer"
    )
