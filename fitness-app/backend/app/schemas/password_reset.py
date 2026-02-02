"""
Password Reset schemas for request/response validation
"""
from pydantic import BaseModel, EmailStr, Field, validator


class PasswordResetRequest(BaseModel):
    """Schema for requesting a password reset code"""
    email: EmailStr


class PasswordResetVerify(BaseModel):
    """Schema for verifying reset code and setting new password"""
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=8, max_length=100)

    @validator('code')
    def validate_code(cls, v):
        """Ensure code is numeric"""
        if not v.isdigit():
            raise ValueError('Code must be 6 digits')
        return v

    @validator('new_password')
    def validate_password(cls, v):
        """Validate password strength"""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v


class PasswordResetRequestResponse(BaseModel):
    """Response for password reset request (always returns success for security)"""
    message: str = "If an account exists with this email, a reset code has been sent."


class PasswordResetVerifyResponse(BaseModel):
    """Response for successful password reset verification"""
    message: str = "Password has been reset successfully."
