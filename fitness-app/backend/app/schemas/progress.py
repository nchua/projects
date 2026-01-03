"""
Progress and Achievement schemas
"""
from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class UserProgressResponse(BaseModel):
    """User's current progress summary"""
    total_xp: int
    level: int
    rank: str
    current_streak: int
    longest_streak: int
    total_workouts: int
    total_volume_lb: int
    total_prs: int
    xp_to_next_level: int
    level_progress: float  # 0.0 - 1.0
    last_workout_date: Optional[str] = None

    class Config:
        from_attributes = True


class XPAwardRequest(BaseModel):
    """Manual XP award request (admin use)"""
    amount: int
    reason: Optional[str] = None


class XPAwardResponse(BaseModel):
    """Response after XP is awarded"""
    xp_earned: int
    streak_bonus: int = 0
    total_xp: int
    old_level: int
    new_level: int
    leveled_up: bool
    levels_gained: int = 0
    old_rank: str
    new_rank: str
    rank_changed: bool
    current_streak: int
    xp_to_next_level: int
    level_progress: float
    achievements_unlocked: List[Dict[str, Any]] = []


class AchievementResponse(BaseModel):
    """Achievement data"""
    id: str
    name: str
    description: str
    category: str
    icon: str
    xp_reward: int
    rarity: str
    unlocked: bool = False
    unlocked_at: Optional[str] = None

    class Config:
        from_attributes = True


class AchievementsListResponse(BaseModel):
    """List of all achievements with unlock status"""
    achievements: List[AchievementResponse]
    total_unlocked: int
    total_available: int


class RecentAchievementsResponse(BaseModel):
    """Recently unlocked achievements"""
    achievements: List[AchievementResponse]
