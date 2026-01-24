"""
Dungeon schemas - Dungeon gate responses and requests
"""
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class DungeonObjectiveResponse(BaseModel):
    """A single dungeon objective with progress"""
    id: str  # UserDungeonObjective ID
    objective_id: str  # DungeonObjectiveDefinition ID
    name: str
    description: str
    objective_type: str
    target_value: int
    progress: int
    is_completed: bool
    is_required: bool
    xp_bonus: int
    order_index: int

    class Config:
        from_attributes = True


class DungeonResponse(BaseModel):
    """A user's dungeon instance"""
    id: str  # UserDungeon ID
    dungeon_id: str  # DungeonDefinition ID
    name: str
    description: str
    rank: str
    status: str

    # Rewards
    base_xp_reward: int
    total_xp_reward: int  # Including stretch bonus

    # Stretch info
    is_stretch_dungeon: bool
    stretch_type: Optional[str] = None  # "stretch" or "very_stretch"
    stretch_bonus_percent: Optional[int] = None  # 25 or 50

    # Timing
    spawned_at: str  # ISO timestamp
    expires_at: str  # ISO timestamp
    accepted_at: Optional[str] = None
    completed_at: Optional[str] = None
    time_remaining_seconds: int
    duration_hours: int

    # Progress
    objectives: List[DungeonObjectiveResponse]
    required_objectives_complete: int
    total_required_objectives: int
    bonus_objectives_complete: int
    total_bonus_objectives: int

    # Flags
    is_boss_dungeon: bool
    is_event_dungeon: bool
    is_rare_gate: bool = False  # Special rare spawn with bonus XP

    class Config:
        from_attributes = True


class DungeonSummaryResponse(BaseModel):
    """Compact dungeon info for lists"""
    id: str
    dungeon_id: str
    name: str
    rank: str
    status: str
    base_xp_reward: int
    is_stretch_dungeon: bool
    stretch_bonus_percent: Optional[int] = None
    time_remaining_seconds: int
    required_objectives_complete: int
    total_required_objectives: int
    is_boss_dungeon: bool
    is_rare_gate: bool = False  # Special rare spawn with bonus XP

    class Config:
        from_attributes = True


class DungeonsResponse(BaseModel):
    """Response with user's dungeons (mission board)"""
    available: List[DungeonSummaryResponse]  # On mission board
    active: List[DungeonSummaryResponse]  # In progress
    completed_unclaimed: List[DungeonSummaryResponse]  # Ready for rewards
    user_level: int
    user_rank: str


class DungeonAcceptResponse(BaseModel):
    """Response after accepting a dungeon"""
    success: bool
    dungeon: DungeonResponse
    message: str


class DungeonAbandonResponse(BaseModel):
    """Response after abandoning a dungeon"""
    success: bool
    message: str


class DungeonClaimResponse(BaseModel):
    """Response after claiming dungeon rewards"""
    success: bool
    xp_earned: int
    stretch_bonus_xp: int
    bonus_objectives_xp: int
    total_xp: int
    level: int
    leveled_up: bool
    new_level: Optional[int] = None
    rank: str
    rank_changed: bool
    new_rank: Optional[str] = None


class DungeonSpawnResponse(BaseModel):
    """Returned in workout response when dungeon spawns"""
    spawned: bool
    dungeon: Optional[DungeonSummaryResponse] = None
    message: Optional[str] = None  # e.g., "A gate has appeared!"


class DungeonProgressUpdateResponse(BaseModel):
    """Progress update after workout"""
    dungeons_progressed: List[str]  # Dungeon IDs that made progress
    dungeons_completed: List[str]  # Dungeon IDs now ready to claim
    objectives_completed: List[str]  # Objective names just completed


class DungeonHistoryResponse(BaseModel):
    """Past dungeon attempts"""
    dungeons: List[DungeonSummaryResponse]
    total_completed: int
    total_abandoned: int
    total_expired: int


# Level requirements for dungeon ranks
DUNGEON_LEVEL_REQUIREMENTS = {
    "E": (1, 15),
    "D": (8, 30),
    "C": (20, 50),
    "B": (35, 75),
    "A": (55, 95),
    "S": (75, None),
    "S+": (85, None),
    "S++": (95, None),
}

# XP rewards by rank
DUNGEON_BASE_XP_BY_RANK = {
    "E": 150,
    "D": 250,
    "C": 400,
    "B": 650,
    "A": 1000,
    "S": 1500,
    "S+": 2000,
    "S++": 3000,
}

# Duration hours by rank
DUNGEON_DURATION_BY_RANK = {
    "E": 72,   # 3 days
    "D": 72,   # 3 days
    "C": 96,   # 4 days
    "B": 120,  # 5 days
    "A": 144,  # 6 days
    "S": 168,  # 7 days
    "S+": 168, # 7 days
    "S++": 168, # 7 days
}
