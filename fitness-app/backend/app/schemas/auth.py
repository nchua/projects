"""
Authentication schemas for request/response validation
"""
from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional


class UserRegister(BaseModel):
    """Schema for user registration"""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)

    @validator('password')
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
