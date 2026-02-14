"""
Password Reset API endpoints
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import hash_password
from app.models.user import User
from app.models.password_reset import PasswordResetToken, generate_reset_code
from app.schemas.password_reset import (
    PasswordResetRequest,
    PasswordResetVerify,
    PasswordResetRequestResponse,
    PasswordResetVerifyResponse,
)
from app.services.email_service import send_password_reset_email
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Security constants
CODE_EXPIRY_MINUTES = 15
MAX_ATTEMPTS = 5
COOLDOWN_MINUTES = 2


@router.post("/request", response_model=PasswordResetRequestResponse)
async def request_password_reset(
    request_data: PasswordResetRequest,
    db: Session = Depends(get_db)
):
    """
    Request a password reset code

    Always returns success to prevent email enumeration.
    If the email exists, sends a 6-digit code.

    Rate limited: one request per email every 2 minutes.
    """
    email = request_data.email.lower()

    # Check for recent reset request (rate limiting)
    recent_token = db.query(PasswordResetToken).filter(
        PasswordResetToken.email == email,
        PasswordResetToken.created_at > datetime.utcnow() - timedelta(minutes=COOLDOWN_MINUTES),
        PasswordResetToken.used_at.is_(None)
    ).first()

    if recent_token:
        # Still return success to prevent enumeration
        logger.info(f"Rate limited password reset request for {email}")
        return PasswordResetRequestResponse()

    # Find user by email
    user = db.query(User).filter(User.email == email).first()

    if user and not user.is_deleted:
        # Generate code and create token
        code = generate_reset_code()
        expires_at = datetime.utcnow() + timedelta(minutes=CODE_EXPIRY_MINUTES)

        # Invalidate any existing unused tokens for this user
        db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None)
        ).update({"used_at": datetime.utcnow()})

        # Create new token
        reset_token = PasswordResetToken(
            user_id=user.id,
            email=email,
            code=code,
            expires_at=expires_at
        )
        db.add(reset_token)
        db.commit()

        # Send email
        email_sent = send_password_reset_email(email, code)
        if not email_sent:
            logger.error(f"Failed to send password reset email to {email}")
            # Still return success to prevent enumeration
        else:
            logger.info(f"Password reset code sent to {email}")
    else:
        logger.info(f"Password reset requested for non-existent email: {email}")

    # Always return success to prevent email enumeration
    return PasswordResetRequestResponse()


@router.post("/verify", response_model=PasswordResetVerifyResponse)
async def verify_password_reset(
    verify_data: PasswordResetVerify,
    db: Session = Depends(get_db)
):
    """
    Verify reset code and update password

    Validates the code, checks expiration and attempt limits,
    then updates the user's password.
    """
    email = verify_data.email.lower()

    # Find the most recent unused token for this email
    token = db.query(PasswordResetToken).filter(
        PasswordResetToken.email == email,
        PasswordResetToken.used_at.is_(None),
        PasswordResetToken.expires_at > datetime.utcnow()
    ).order_by(PasswordResetToken.created_at.desc()).first()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset code. Please request a new one."
        )

    # Check attempt limit
    if token.attempts >= MAX_ATTEMPTS:
        # Mark token as used to prevent further attempts
        token.used_at = datetime.utcnow()
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Too many attempts. Please request a new reset code."
        )

    # Increment attempts
    token.attempts += 1
    db.commit()

    # Verify code
    if token.code != verify_data.code:
        remaining = MAX_ATTEMPTS - token.attempts
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid code. {remaining} attempts remaining."
        )

    # Code is valid - update password
    user = db.query(User).filter(User.id == token.user_id).first()
    if not user or user.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not found."
        )

    # Hash and update password
    user.password_hash = hash_password(verify_data.new_password)
    user.updated_at = datetime.utcnow()

    # Mark token as used
    token.used_at = datetime.utcnow()

    db.commit()
    logger.info(f"Password reset successful for user {user.id}")

    return PasswordResetVerifyResponse()
