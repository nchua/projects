"""
User schemas for request/response validation
"""
import re
from pydantic import BaseModel, Field, field_validator
from typing import Optional


# Username validation pattern: 3-20 chars, lowercase, alphanumeric + underscore
# No leading/trailing underscores
USERNAME_PATTERN = re.compile(r'^[a-z0-9][a-z0-9_]{1,18}[a-z0-9]$|^[a-z0-9]{3}$')


class UsernameUpdate(BaseModel):
    """Schema for setting/updating username"""
    username: str = Field(..., min_length=3, max_length=20)

    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        # Convert to lowercase
        v = v.lower()

        # Check pattern
        if not USERNAME_PATTERN.match(v):
            if v.startswith('_') or v.endswith('_'):
                raise ValueError('Username cannot start or end with underscore')
            if not all(c.isalnum() or c == '_' for c in v):
                raise ValueError('Username can only contain letters, numbers, and underscores')
            raise ValueError('Invalid username format')

        return v


class UsernameCheckResponse(BaseModel):
    """Schema for username availability check response"""
    username: str
    available: bool


class UserPublicResponse(BaseModel):
    """Schema for public user information (for search results, friend lists)"""
    id: str
    username: str
    rank: str
    level: int

    class Config:
        from_attributes = True
