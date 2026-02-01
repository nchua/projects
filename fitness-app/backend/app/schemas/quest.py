"""
Quest schemas - Daily quest responses
"""
from pydantic import BaseModel
from typing import Optional, List


class QuestResponse(BaseModel):
    """A single quest with progress"""
    id: str  # UserQuest ID
    quest_id: str  # QuestDefinition ID
    name: str
    description: str
    quest_type: str
    target_value: int
    xp_reward: int
    progress: int
    is_completed: bool
    is_claimed: bool
    difficulty: str
    completed_by_workout_id: Optional[str] = None  # ID of workout that completed this quest

    class Config:
        from_attributes = True


class DailyQuestsResponse(BaseModel):
    """Response with today's daily quests"""
    quests: List[QuestResponse]
    refresh_at: str  # ISO timestamp for next refresh (midnight UTC)
    completed_count: int
    total_count: int


class QuestClaimResponse(BaseModel):
    """Response after claiming a quest reward"""
    success: bool
    xp_earned: int
    total_xp: int
    level: int
    leveled_up: bool
    new_level: Optional[int] = None
    rank: str
    rank_changed: bool
    new_rank: Optional[str] = None


class QuestsCompletedResponse(BaseModel):
    """Quests completed by a workout"""
    quest_ids: List[str]
    quest_names: List[str]
