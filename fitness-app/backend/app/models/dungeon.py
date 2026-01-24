"""
Dungeon models - Solo Leveling inspired gate/dungeon system
"""
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Float
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from app.core.database import Base


class DungeonRank(str, enum.Enum):
    """Dungeon difficulty ranks - matches Solo Leveling gates"""
    E = "E"
    D = "D"
    C = "C"
    B = "B"
    A = "A"
    S = "S"
    S_PLUS = "S+"
    S_PLUS_PLUS = "S++"


class DungeonObjectiveType(str, enum.Enum):
    """Types of dungeon objectives"""
    TOTAL_REPS = "total_reps"               # Complete X reps across workouts
    TOTAL_VOLUME = "total_volume"           # Lift X total weight (lbs)
    TOTAL_SETS = "total_sets"               # Complete X sets
    COMPOUND_SETS = "compound_sets"         # X sets of compound lifts
    WORKOUT_COUNT = "workout_count"         # Complete X workouts
    EXERCISE_SPECIFIC = "exercise_specific" # X sets of specific exercise
    PR_ACHIEVED = "pr_achieved"             # Set X PRs
    STREAK_MAINTAIN = "streak_maintain"     # Maintain streak for X days


class DungeonStatus(str, enum.Enum):
    """User dungeon states"""
    AVAILABLE = "available"     # On mission board, not accepted
    ACTIVE = "active"           # Accepted, in progress
    COMPLETED = "completed"     # All required objectives done
    CLAIMED = "claimed"         # Rewards claimed
    EXPIRED = "expired"         # Time ran out
    ABANDONED = "abandoned"     # User gave up


class DungeonDefinition(Base):
    """Master definitions for dungeon types (templates)"""
    __tablename__ = "dungeon_definitions"

    id = Column(String, primary_key=True)  # e.g., "goblin_cave_e"
    name = Column(String, nullable=False)  # e.g., "Goblin Cave"
    description = Column(String, nullable=False)
    rank = Column(String, nullable=False)  # DungeonRank value

    # Timing
    duration_hours = Column(Integer, default=72, nullable=False)  # Time limit

    # Rewards
    base_xp_reward = Column(Integer, nullable=False)
    bonus_objectives_multiplier = Column(Float, default=1.2)  # Bonus for completing all

    # Spawn configuration
    spawn_weight = Column(Integer, default=100)  # Relative spawn chance
    min_user_level = Column(Integer, default=1)
    max_user_level = Column(Integer, nullable=True)  # null = no max

    # Flags
    is_active = Column(Boolean, default=True)
    is_boss_dungeon = Column(Boolean, default=False)
    is_event_dungeon = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    objectives = relationship("DungeonObjectiveDefinition", back_populates="dungeon", cascade="all, delete-orphan")
    user_dungeons = relationship("UserDungeon", back_populates="definition")


class DungeonObjectiveDefinition(Base):
    """Objective templates within a dungeon definition"""
    __tablename__ = "dungeon_objective_definitions"

    id = Column(String, primary_key=True)  # e.g., "goblin_cave_e_obj_1"
    dungeon_id = Column(String, ForeignKey("dungeon_definitions.id"), nullable=False)

    name = Column(String, nullable=False)  # e.g., "Clear the Cave"
    description = Column(String, nullable=False)
    objective_type = Column(String, nullable=False)  # DungeonObjectiveType value
    target_value = Column(Integer, nullable=False)
    target_exercise_id = Column(String, ForeignKey("exercises.id"), nullable=True)

    order_index = Column(Integer, default=0)  # Display order
    is_required = Column(Boolean, default=True)  # Optional bonus objectives
    xp_bonus = Column(Integer, default=0)  # Additional XP for this objective

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    dungeon = relationship("DungeonDefinition", back_populates="objectives")


class UserDungeon(Base):
    """User's dungeon instances"""
    __tablename__ = "user_dungeons"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    dungeon_id = Column(String, ForeignKey("dungeon_definitions.id"), nullable=False)

    status = Column(String, default="available", nullable=False)  # DungeonStatus

    # Timing
    spawned_at = Column(DateTime, nullable=False)  # When gate appeared
    accepted_at = Column(DateTime, nullable=True)  # When user entered
    expires_at = Column(DateTime, nullable=False)  # Deadline
    completed_at = Column(DateTime, nullable=True)
    claimed_at = Column(DateTime, nullable=True)

    # Rewards (calculated at completion)
    xp_earned = Column(Integer, default=0)
    stretch_bonus_xp = Column(Integer, default=0)  # Bonus for higher difficulty

    # Metadata
    is_stretch_dungeon = Column(Boolean, default=False)  # Above user's level
    stretch_type = Column(String, nullable=True)  # "stretch" or "very_stretch"
    is_rare_gate = Column(Boolean, default=False)  # Special rare spawn with bonus XP

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    definition = relationship("DungeonDefinition", back_populates="user_dungeons")
    objectives = relationship("UserDungeonObjective", back_populates="user_dungeon", cascade="all, delete-orphan")


class UserDungeonObjective(Base):
    """User's progress on individual dungeon objectives"""
    __tablename__ = "user_dungeon_objectives"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_dungeon_id = Column(String, ForeignKey("user_dungeons.id"), nullable=False)
    objective_definition_id = Column(String, ForeignKey("dungeon_objective_definitions.id"), nullable=False)

    progress = Column(Integer, default=0, nullable=False)
    is_completed = Column(Boolean, default=False, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user_dungeon = relationship("UserDungeon", back_populates="objectives")
    objective_definition = relationship("DungeonObjectiveDefinition")
