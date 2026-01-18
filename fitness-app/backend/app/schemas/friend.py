"""
Friend schemas for request/response validation
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class FriendRequestCreate(BaseModel):
    """Schema for sending a friend request"""
    receiver_id: str = Field(..., description="ID of the user to send request to")


class FriendRequestResponse(BaseModel):
    """Schema for friend request in responses"""
    id: str
    sender_id: str
    sender_username: Optional[str] = None
    sender_rank: Optional[str] = None
    sender_level: Optional[int] = None
    receiver_id: str
    receiver_username: Optional[str] = None
    receiver_rank: Optional[str] = None
    receiver_level: Optional[int] = None
    status: str
    created_at: str

    class Config:
        from_attributes = True


class FriendRequestsResponse(BaseModel):
    """Schema for all friend requests (incoming + sent)"""
    incoming: List[FriendRequestResponse] = []
    sent: List[FriendRequestResponse] = []


class FriendResponse(BaseModel):
    """Schema for friend in responses"""
    id: str  # Friendship ID
    user_id: str
    friend_id: str
    friend_username: Optional[str] = None
    friend_rank: Optional[str] = None
    friend_level: Optional[int] = None
    created_at: str
    last_workout_at: Optional[str] = None

    class Config:
        from_attributes = True


class RecentWorkoutResponse(BaseModel):
    """Schema for recent workout in friend profile"""
    id: str
    date: str
    exercise_count: int
    exercise_names: List[str] = []
    xp_earned: Optional[int] = None


class FriendProfileResponse(BaseModel):
    """Schema for friend's profile with stats and activity"""
    user_id: str
    username: Optional[str] = None
    rank: Optional[str] = None
    level: Optional[int] = None
    total_workouts: int = 0
    current_streak: int = 0
    total_prs: int = 0
    recent_workouts: List[RecentWorkoutResponse] = []

    class Config:
        from_attributes = True
