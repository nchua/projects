"""
Authentication API endpoints
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.rate_limit import AUTH_RATE_LIMIT, limiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
    verify_password_with_rehash,
    verify_token,
)
from app.core.utils import to_iso8601_utc
from app.models.user import User, UserProfile
from app.schemas.auth import (
    DeleteAccountRequest,
    RegisterResponse,
    Token,
    TokenRefresh,
    UserLogin,
    UserRegister,
    UserResponse,
)

# Generic success message returned by /auth/register regardless of whether the
# email was new or already taken. This closes the email-enumeration oracle:
# an attacker probing /auth/register cannot distinguish "fresh account" from
# "existing account" because the status code and response body shape are the
# same in both cases. Real users discover duplicate-email collisions at login
# time (their "new" password won't match the existing stored hash).
# TODO: once an email-verification pipeline exists, switch to the stronger
# pattern of sending a verification / "someone tried to register your email"
# message out-of-band instead of faking a success response.
_REGISTER_GENERIC_MESSAGE = "User registered successfully"

router = APIRouter()


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(AUTH_RATE_LIMIT)
async def register(request: Request, user_data: UserRegister, db: Session = Depends(get_db)):
    """
    Register a new user account.

    Returns an identical-shape response whether the email was new or already
    registered to avoid leaking account existence (email enumeration). On
    duplicate email we simply no-op rather than creating a second row, but
    the caller sees the same status code and JSON shape as a fresh signup.
    A real user whose email collides discovers the collision at login time.
    """
    existing_user = db.query(User).filter(User.email == user_data.email).first()

    if existing_user is None:
        # Fresh account path.
        password_hash = hash_password(user_data.password)
        new_user = User(
            email=user_data.email,
            password_hash=password_hash,
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        default_profile = UserProfile(user_id=new_user.id)
        db.add(default_profile)
        db.commit()

        user_response = UserResponse(
            id=new_user.id,
            email=new_user.email,
            created_at=to_iso8601_utc(new_user.created_at),
        )
    else:
        # Duplicate email path: return the same response shape but with a
        # synthetic id and current timestamp so the response is
        # indistinguishable from a fresh registration. Crucially we do NOT
        # expose the real user's id or created_at — either would let an
        # attacker correlate probes and confirm the account exists.
        user_response = UserResponse(
            id=str(uuid.uuid4()),
            email=user_data.email,
            created_at=to_iso8601_utc(datetime.now(timezone.utc)),
        )

    return RegisterResponse(
        message=_REGISTER_GENERIC_MESSAGE,
        user=user_response,
    )


@router.post("/login", response_model=Token)
@limiter.limit(AUTH_RATE_LIMIT)
async def login(request: Request, user_data: UserLogin, db: Session = Depends(get_db)):
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

    # Reject deleted users
    if user.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account scheduled for deletion. Contact support to recover.",
        )

    # Verify password. The helper returns (ok, needs_rehash); the second
    # flag is True when the stored hash is the legacy raw-bcrypt format,
    # giving us a transparent migration point to re-store under the new
    # sha256-prehash + bcrypt scheme on next successful login.
    ok, needs_rehash = verify_password_with_rehash(user_data.password, user.password_hash)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if needs_rehash:
        user.password_hash = hash_password(user_data.password)
        db.commit()

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

    # Reject deleted users
    if user.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account has been deleted",
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


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    request: DeleteAccountRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Soft-delete the current user's account.

    Requires password confirmation. Account will be inaccessible immediately
    and permanently deleted after 30 days.
    """
    if not verify_password(request.password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
        )

    from datetime import datetime, timezone
    current_user.is_deleted = True
    current_user.deleted_at = datetime.now(timezone.utc)
    db.commit()

    return None
