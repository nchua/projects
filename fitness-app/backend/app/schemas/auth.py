"""
Authentication schemas for request/response validation
"""

import string

from pydantic import BaseModel, EmailStr, Field, validator

# NIST 800-63B leans toward length over character-class complexity, but in
# the absence of a breached-password check we keep both signals. 12 chars
# is short enough to still be memorable (or auto-generated) and long enough
# to make basic brute force infeasible at the login rate limit we enforce.
MIN_PASSWORD_LENGTH = 12
PASSWORD_SYMBOLS = set(string.punctuation)


class UserRegister(BaseModel):
    """Schema for user registration"""
    email: EmailStr
    password: str = Field(..., min_length=MIN_PASSWORD_LENGTH, max_length=100)

    @validator('password')
    def validate_password(cls, v):
        """Validate password strength."""
        if len(v) < MIN_PASSWORD_LENGTH:
            raise ValueError(
                f'Password must be at least {MIN_PASSWORD_LENGTH} characters long'
            )
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        if not any(c in PASSWORD_SYMBOLS for c in v):
            raise ValueError('Password must contain at least one symbol (e.g. !@#$%^&*)')
        return v


class UserLogin(BaseModel):
    """Schema for user login"""
    email: EmailStr
    password: str


class Token(BaseModel):
    """Schema for JWT token response"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefresh(BaseModel):
    """Schema for token refresh request"""
    refresh_token: str


class UserResponse(BaseModel):
    """Schema for user information in responses"""
    id: str
    email: str
    created_at: str

    class Config:
        from_attributes = True


class RegisterResponse(BaseModel):
    """Schema for registration success response"""
    message: str
    user: UserResponse


class DeleteAccountRequest(BaseModel):
    """Schema for account deletion confirmation"""
    password: str
