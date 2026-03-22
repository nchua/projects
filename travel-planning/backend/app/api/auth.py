"""Auth endpoints: register, login, Apple Sign-In, token refresh."""

import logging
import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_apple_identity_token,
    verify_password,
)
from app.models.enums import AuthProvider
from app.models.user import User
from app.schemas.auth import (
    AppleAuthRequest,
    AuthResponse,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
)
from app.schemas.user import UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _build_tokens(user: User) -> dict[str, str]:
    """Create access and refresh tokens for a user."""
    token_data = {"sub": str(user.id)}
    return {
        "access_token": create_access_token(token_data),
        "refresh_token": create_refresh_token(token_data),
    }


def _build_auth_response(user: User) -> AuthResponse:
    """Build a full AuthResponse with tokens and user profile."""
    tokens = _build_tokens(user)
    return AuthResponse(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        user=UserResponse.model_validate(user),
    )


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Register a new user with email and password."""
    email = body.email.lower()

    # Check for existing email
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
            headers={"X-Error-Code": "EMAIL_EXISTS"},
        )

    user = User(
        email=email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        auth_provider=AuthProvider.email,
        timezone=body.timezone,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    return _build_auth_response(user)


@router.post("/login", response_model=AuthResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Authenticate with email and password."""
    email = body.email.lower()

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None or user.password_hash is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"X-Error-Code": "INVALID_CREDENTIALS"},
        )

    if not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"X-Error-Code": "INVALID_CREDENTIALS"},
        )

    return _build_auth_response(user)


@router.post("/apple", response_model=AuthResponse)
async def apple_auth(
    body: AppleAuthRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Sign in with Apple. Creates account on first use."""
    # Verify the Apple identity token
    try:
        claims = await verify_apple_identity_token(body.identity_token)
    except ValueError as e:
        logger.warning("Apple token verification failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Apple identity token",
            headers={"X-Error-Code": "INVALID_APPLE_TOKEN"},
        )

    apple_user_id: str = claims["sub"]
    apple_email: str | None = claims.get("email")

    # Look up by Apple user ID
    result = await db.execute(
        select(User).where(User.apple_user_id == apple_user_id)
    )
    user = result.scalar_one_or_none()

    if user is not None:
        # Existing Apple user — return tokens
        return _build_auth_response(user)

    # Check if email matches an existing email-auth user (link accounts)
    if apple_email:
        result = await db.execute(
            select(User).where(User.email == apple_email.lower())
        )
        user = result.scalar_one_or_none()

        if user is not None:
            # Link Apple ID to existing email user
            user.apple_user_id = apple_user_id
            if body.display_name and not user.display_name:
                user.display_name = body.display_name
            await db.flush()
            await db.refresh(user)
            return _build_auth_response(user)

    # New user — create account
    user = User(
        email=(apple_email or f"{apple_user_id}@privaterelay.appleid.com").lower(),
        auth_provider=AuthProvider.apple,
        apple_user_id=apple_user_id,
        display_name=body.display_name,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    response = _build_auth_response(user)
    # Return 201 for newly created users (caller can check via status code)
    return response


@router.post("/refresh", response_model=AuthResponse)
async def refresh_token(
    body: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Exchange a refresh token for a new access/refresh token pair."""
    try:
        payload = decode_token(body.refresh_token)
        user_id_str: str | None = payload.get("sub")
        token_type: str | None = payload.get("type")

        if user_id_str is None or token_type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
                headers={"X-Error-Code": "INVALID_REFRESH_TOKEN"},
            )

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"X-Error-Code": "INVALID_REFRESH_TOKEN"},
        )

    user_id = _uuid.UUID(user_id_str)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"X-Error-Code": "INVALID_REFRESH_TOKEN"},
        )

    return _build_auth_response(user)
