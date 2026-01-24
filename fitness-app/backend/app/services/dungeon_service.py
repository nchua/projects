"""
Dungeon Service - Gate spawning, progress tracking, and rewards
"""
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
import random
import uuid

from app.models.dungeon import (
    DungeonDefinition, DungeonObjectiveDefinition,
    UserDungeon, UserDungeonObjective,
    DungeonRank, DungeonObjectiveType, DungeonStatus
)
from app.models.workout import WorkoutSession
from app.models.progress import UserProgress
from app.services.xp_service import (
    get_or_create_user_progress, xp_for_level, get_rank_for_level
)
from app.schemas.dungeon import (
    DUNGEON_LEVEL_REQUIREMENTS,
    DUNGEON_BASE_XP_BY_RANK,
    DUNGEON_DURATION_BY_RANK
)


# Spawn configuration
BASE_SPAWN_CHANCE = 0.20  # 20% base chance
SPAWN_PENALTY_PER_AVAILABLE = 0.05  # -5% per available dungeon
MAX_AVAILABLE_DUNGEONS = 5  # Maximum dungeons on mission board
MIN_AVAILABLE_DUNGEONS = 3  # Minimum dungeons to always have available
STRETCH_LEVEL_THRESHOLD = 10  # Can't attempt more than 10 levels above
RARE_GATE_CHANCE = 0.05  # 5% chance for a rare gate (higher rank)

# Compound exercises for quest checking
COMPOUND_EXERCISES = [
    "back squat", "squat", "front squat",
    "bench press", "flat bench", "incline bench",
    "deadlift", "conventional deadlift", "sumo deadlift", "romanian deadlift",
    "overhead press", "shoulder press", "military press",
    "barbell row", "bent over row", "pendlay row"
]


def calculate_spawn_chance(user_level: int, available_count: int) -> float:
    """
    Calculate dungeon spawn chance after a workout.

    Args:
        user_level: User's current level
        available_count: Number of dungeons already available

    Returns:
        Spawn probability (0.0 - 1.0)
    """
    # Base chance reduced by number of available dungeons
    available_penalty = available_count * SPAWN_PENALTY_PER_AVAILABLE

    # Slight increase at higher levels (1% per 10 levels, max 5%)
    level_bonus = min(0.05, user_level * 0.001)

    return max(0.05, BASE_SPAWN_CHANCE - available_penalty + level_bonus)


def get_stretch_info(user_level: int, dungeon_min_level: int) -> Tuple[bool, Optional[str], int]:
    """
    Determine if a dungeon is a stretch for the user.

    Returns:
        (is_accessible, stretch_type, bonus_percent)
        - is_accessible: Can user attempt this dungeon?
        - stretch_type: None, "stretch", or "very_stretch"
        - bonus_percent: XP bonus percentage (0, 25, or 50)
    """
    level_diff = dungeon_min_level - user_level

    if level_diff > STRETCH_LEVEL_THRESHOLD:
        return (False, None, 0)  # Cannot attempt
    elif level_diff > 5:
        return (True, "very_stretch", 50)  # 50% bonus
    elif level_diff > 0:
        return (True, "stretch", 25)  # 25% bonus
    else:
        return (True, None, 0)  # Standard


def get_eligible_dungeons(db: Session, user_level: int) -> List[DungeonDefinition]:
    """
    Get dungeons eligible for this user based on level.

    Includes dungeons up to STRETCH_LEVEL_THRESHOLD above user's level.
    """
    # Calculate maximum level we can attempt
    max_min_level = user_level + STRETCH_LEVEL_THRESHOLD

    dungeons = db.query(DungeonDefinition).filter(
        DungeonDefinition.is_active == True,
        DungeonDefinition.min_user_level <= max_min_level
    ).all()

    # Filter out dungeons with max_user_level below user's level
    eligible = []
    for d in dungeons:
        if d.max_user_level is None or d.max_user_level >= user_level:
            eligible.append(d)

    return eligible


def maybe_spawn_dungeon(
    db: Session,
    user_id: str,
    force: bool = False,
    force_rare: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Possibly spawn a new dungeon after a workout.

    Args:
        db: Database session
        user_id: User ID
        force: Force spawn (for testing)
        force_rare: Force a rare gate spawn (for testing)

    Returns:
        Dungeon spawn data if spawned, None otherwise
    """
    # Get user progress
    progress = get_or_create_user_progress(db, user_id)

    # Count available dungeons
    available_count = db.query(UserDungeon).filter(
        UserDungeon.user_id == user_id,
        UserDungeon.status == DungeonStatus.AVAILABLE.value
    ).count()

    # Check if at max available dungeons (force bypasses this limit)
    if not force and available_count >= MAX_AVAILABLE_DUNGEONS:
        return None

    # Roll for spawn (force bypasses the random roll)
    if not force:
        spawn_chance = calculate_spawn_chance(progress.level, available_count)
        if random.random() > spawn_chance:
            return None

    # Get eligible dungeons
    eligible = get_eligible_dungeons(db, progress.level)
    if not eligible:
        return None

    # Check for rare gate (5% chance or forced)
    is_rare_gate = force_rare or random.random() < RARE_GATE_CHANCE

    if is_rare_gate:
        # For rare gates, try to find a higher-rank dungeon
        selected = _select_rare_dungeon(eligible, progress.level)
    else:
        # Weighted random selection based on spawn_weight
        total_weight = sum(d.spawn_weight for d in eligible)
        roll = random.uniform(0, total_weight)
        cumulative = 0
        selected = eligible[0]

        for dungeon in eligible:
            cumulative += dungeon.spawn_weight
            if roll <= cumulative:
                selected = dungeon
                break

    # Calculate stretch info
    is_accessible, stretch_type, bonus_percent = get_stretch_info(
        progress.level, selected.min_user_level
    )

    # Create user dungeon
    now = datetime.utcnow()
    expires_at = now + timedelta(hours=selected.duration_hours)

    user_dungeon = UserDungeon(
        id=str(uuid.uuid4()),
        user_id=user_id,
        dungeon_id=selected.id,
        status=DungeonStatus.AVAILABLE.value,
        spawned_at=now,
        expires_at=expires_at,
        is_stretch_dungeon=stretch_type is not None,
        stretch_type=stretch_type,
        is_rare_gate=is_rare_gate
    )
    db.add(user_dungeon)

    # Create objective progress records
    for obj_def in selected.objectives:
        user_obj = UserDungeonObjective(
            id=str(uuid.uuid4()),
            user_dungeon_id=user_dungeon.id,
            objective_definition_id=obj_def.id,
            progress=0,
            is_completed=False
        )
        db.add(user_obj)

    db.flush()

    # Calculate total XP reward
    base_xp = selected.base_xp_reward
    stretch_bonus = int(base_xp * bonus_percent / 100) if bonus_percent else 0

    # Rare gates message
    if is_rare_gate:
        message = f"⚡ A RARE {selected.rank}-Rank Gate has materialized!"
    else:
        message = f"A {selected.rank}-Rank Gate has appeared!"

    return {
        "spawned": True,
        "dungeon": {
            "id": user_dungeon.id,
            "dungeon_id": selected.id,
            "name": selected.name,
            "rank": selected.rank,
            "status": user_dungeon.status,
            "base_xp_reward": base_xp,
            "is_stretch_dungeon": user_dungeon.is_stretch_dungeon,
            "stretch_bonus_percent": bonus_percent if bonus_percent else None,
            "time_remaining_seconds": int((expires_at - now).total_seconds()),
            "required_objectives_complete": 0,
            "total_required_objectives": sum(1 for o in selected.objectives if o.is_required),
            "is_boss_dungeon": selected.is_boss_dungeon,
            "is_rare_gate": is_rare_gate
        },
        "message": message
    }


def _select_rare_dungeon(eligible: List[DungeonDefinition], user_level: int) -> DungeonDefinition:
    """
    Select a dungeon for a rare gate spawn.

    Prioritizes higher-rank dungeons that are still accessible to the user.
    """
    # Rank order for prioritization
    rank_order = ["S++", "S+", "S", "A", "B", "C", "D", "E"]

    # Sort eligible dungeons by rank (highest first)
    sorted_dungeons = sorted(
        eligible,
        key=lambda d: rank_order.index(d.rank) if d.rank in rank_order else 99
    )

    # Try to find a dungeon at least one rank higher than typical for user level
    # Pick from the top 30% of eligible dungeons by rank
    high_rank_count = max(1, len(sorted_dungeons) // 3)
    high_rank_dungeons = sorted_dungeons[:high_rank_count]

    # Return a random one from the high-rank pool
    return random.choice(high_rank_dungeons)


def ensure_minimum_dungeons(db: Session, user_id: str) -> List[Dict[str, Any]]:
    """
    Ensure the user has at least MIN_AVAILABLE_DUNGEONS available.

    Called when loading the dungeon board to auto-replenish gates.

    Args:
        db: Database session
        user_id: User ID

    Returns:
        List of newly spawned dungeons
    """
    # Count current available dungeons
    available_count = db.query(UserDungeon).filter(
        UserDungeon.user_id == user_id,
        UserDungeon.status == DungeonStatus.AVAILABLE.value,
        UserDungeon.expires_at > datetime.utcnow()  # Not expired
    ).count()

    spawned = []
    dungeons_needed = MIN_AVAILABLE_DUNGEONS - available_count

    for _ in range(dungeons_needed):
        # Force spawn but still allow rare gate chance
        result = maybe_spawn_dungeon(db, user_id, force=True)
        if result:
            spawned.append(result)

    return spawned


def get_user_dungeons(db: Session, user_id: str) -> Dict[str, Any]:
    """
    Get all user dungeons organized by status.

    Automatically ensures minimum dungeons are available.

    Returns:
        Dict with available, active, and completed_unclaimed lists
    """
    progress = get_or_create_user_progress(db, user_id)
    now = datetime.utcnow()

    # Auto-replenish dungeons if below minimum
    ensure_minimum_dungeons(db, user_id)

    # Get all non-terminal dungeons
    user_dungeons = db.query(UserDungeon).filter(
        UserDungeon.user_id == user_id,
        UserDungeon.status.in_([
            DungeonStatus.AVAILABLE.value,
            DungeonStatus.ACTIVE.value,
            DungeonStatus.COMPLETED.value
        ])
    ).all()

    available = []
    active = []
    completed_unclaimed = []

    for ud in user_dungeons:
        # Check if expired
        if ud.expires_at < now and ud.status in [
            DungeonStatus.AVAILABLE.value,
            DungeonStatus.ACTIVE.value
        ]:
            ud.status = DungeonStatus.EXPIRED.value
            continue

        summary = build_dungeon_summary(ud, now)

        if ud.status == DungeonStatus.AVAILABLE.value:
            available.append(summary)
        elif ud.status == DungeonStatus.ACTIVE.value:
            active.append(summary)
        elif ud.status == DungeonStatus.COMPLETED.value:
            completed_unclaimed.append(summary)

    db.flush()

    return {
        "available": available,
        "active": active,
        "completed_unclaimed": completed_unclaimed,
        "user_level": progress.level,
        "user_rank": progress.rank
    }


def build_dungeon_summary(user_dungeon: UserDungeon, now: datetime) -> Dict[str, Any]:
    """Build a summary dict for a user dungeon."""
    definition = user_dungeon.definition

    # Count objectives
    required_complete = sum(
        1 for o in user_dungeon.objectives
        if o.is_completed and o.objective_definition.is_required
    )
    total_required = sum(
        1 for o in user_dungeon.objectives
        if o.objective_definition.is_required
    )

    # Calculate stretch bonus
    stretch_bonus_percent = None
    if user_dungeon.stretch_type == "stretch":
        stretch_bonus_percent = 25
    elif user_dungeon.stretch_type == "very_stretch":
        stretch_bonus_percent = 50

    return {
        "id": user_dungeon.id,
        "dungeon_id": definition.id,
        "name": definition.name,
        "rank": definition.rank,
        "status": user_dungeon.status,
        "base_xp_reward": definition.base_xp_reward,
        "is_stretch_dungeon": user_dungeon.is_stretch_dungeon,
        "stretch_bonus_percent": stretch_bonus_percent,
        "time_remaining_seconds": max(0, int((user_dungeon.expires_at - now).total_seconds())),
        "required_objectives_complete": required_complete,
        "total_required_objectives": total_required,
        "is_boss_dungeon": definition.is_boss_dungeon,
        "is_rare_gate": user_dungeon.is_rare_gate
    }


def get_dungeon_detail(db: Session, user_id: str, user_dungeon_id: str) -> Optional[Dict[str, Any]]:
    """Get detailed dungeon info with all objectives."""
    user_dungeon = db.query(UserDungeon).filter(
        UserDungeon.id == user_dungeon_id,
        UserDungeon.user_id == user_id
    ).first()

    if not user_dungeon:
        return None

    definition = user_dungeon.definition
    now = datetime.utcnow()

    # Build objectives list
    objectives = []
    required_complete = 0
    total_required = 0
    bonus_complete = 0
    total_bonus = 0

    for user_obj in sorted(user_dungeon.objectives, key=lambda o: o.objective_definition.order_index):
        obj_def = user_obj.objective_definition
        objectives.append({
            "id": user_obj.id,
            "objective_id": obj_def.id,
            "name": obj_def.name,
            "description": obj_def.description,
            "objective_type": obj_def.objective_type,
            "target_value": obj_def.target_value,
            "progress": user_obj.progress,
            "is_completed": user_obj.is_completed,
            "is_required": obj_def.is_required,
            "xp_bonus": obj_def.xp_bonus,
            "order_index": obj_def.order_index
        })

        if obj_def.is_required:
            total_required += 1
            if user_obj.is_completed:
                required_complete += 1
        else:
            total_bonus += 1
            if user_obj.is_completed:
                bonus_complete += 1

    # Calculate rewards
    stretch_bonus_percent = None
    if user_dungeon.stretch_type == "stretch":
        stretch_bonus_percent = 25
    elif user_dungeon.stretch_type == "very_stretch":
        stretch_bonus_percent = 50

    base_xp = definition.base_xp_reward
    stretch_bonus = int(base_xp * stretch_bonus_percent / 100) if stretch_bonus_percent else 0
    total_xp = base_xp + stretch_bonus

    return {
        "id": user_dungeon.id,
        "dungeon_id": definition.id,
        "name": definition.name,
        "description": definition.description,
        "rank": definition.rank,
        "status": user_dungeon.status,
        "base_xp_reward": base_xp,
        "total_xp_reward": total_xp,
        "is_stretch_dungeon": user_dungeon.is_stretch_dungeon,
        "stretch_type": user_dungeon.stretch_type,
        "stretch_bonus_percent": stretch_bonus_percent,
        "spawned_at": user_dungeon.spawned_at.isoformat(),
        "expires_at": user_dungeon.expires_at.isoformat(),
        "accepted_at": user_dungeon.accepted_at.isoformat() if user_dungeon.accepted_at else None,
        "completed_at": user_dungeon.completed_at.isoformat() if user_dungeon.completed_at else None,
        "time_remaining_seconds": max(0, int((user_dungeon.expires_at - now).total_seconds())),
        "duration_hours": definition.duration_hours,
        "objectives": objectives,
        "required_objectives_complete": required_complete,
        "total_required_objectives": total_required,
        "bonus_objectives_complete": bonus_complete,
        "total_bonus_objectives": total_bonus,
        "is_boss_dungeon": definition.is_boss_dungeon,
        "is_event_dungeon": definition.is_event_dungeon,
        "is_rare_gate": user_dungeon.is_rare_gate
    }


def accept_dungeon(db: Session, user_id: str, user_dungeon_id: str) -> Dict[str, Any]:
    """
    Accept and start a dungeon.

    Raises:
        ValueError: If dungeon not found or not available
    """
    user_dungeon = db.query(UserDungeon).filter(
        UserDungeon.id == user_dungeon_id,
        UserDungeon.user_id == user_id
    ).first()

    if not user_dungeon:
        raise ValueError("Dungeon not found")

    if user_dungeon.status != DungeonStatus.AVAILABLE.value:
        raise ValueError(f"Dungeon is not available (status: {user_dungeon.status})")

    # Check if already has an active dungeon
    active_count = db.query(UserDungeon).filter(
        UserDungeon.user_id == user_id,
        UserDungeon.status == DungeonStatus.ACTIVE.value
    ).count()

    if active_count > 0:
        raise ValueError("You already have an active dungeon. Complete or abandon it first.")

    # Check if expired
    now = datetime.utcnow()
    if user_dungeon.expires_at < now:
        user_dungeon.status = DungeonStatus.EXPIRED.value
        db.flush()
        raise ValueError("This gate has closed")

    # Accept the dungeon
    user_dungeon.status = DungeonStatus.ACTIVE.value
    user_dungeon.accepted_at = now

    db.flush()

    detail = get_dungeon_detail(db, user_id, user_dungeon_id)
    return {
        "success": True,
        "dungeon": detail,
        "message": f"You have entered the {user_dungeon.definition.name}!"
    }


def abandon_dungeon(db: Session, user_id: str, user_dungeon_id: str) -> Dict[str, Any]:
    """
    Abandon an active dungeon.

    Raises:
        ValueError: If dungeon not found or not active
    """
    user_dungeon = db.query(UserDungeon).filter(
        UserDungeon.id == user_dungeon_id,
        UserDungeon.user_id == user_id
    ).first()

    if not user_dungeon:
        raise ValueError("Dungeon not found")

    if user_dungeon.status != DungeonStatus.ACTIVE.value:
        raise ValueError("Can only abandon active dungeons")

    user_dungeon.status = DungeonStatus.ABANDONED.value
    db.flush()

    return {
        "success": True,
        "message": "You have retreated from the dungeon. No penalty applied."
    }


def update_dungeon_progress(
    db: Session,
    user_id: str,
    workout: WorkoutSession
) -> Dict[str, Any]:
    """
    Update progress on active dungeons based on completed workout.

    Returns:
        Dict with dungeons_progressed, dungeons_completed, objectives_completed
    """
    now = datetime.utcnow()

    # Get active dungeons
    active_dungeons = db.query(UserDungeon).filter(
        UserDungeon.user_id == user_id,
        UserDungeon.status == DungeonStatus.ACTIVE.value
    ).all()

    if not active_dungeons:
        return {
            "dungeons_progressed": [],
            "dungeons_completed": [],
            "objectives_completed": []
        }

    # Calculate workout stats
    total_reps = 0
    compound_sets = 0
    total_volume = 0
    total_sets = 0

    for workout_exercise in workout.workout_exercises:
        exercise_name = workout_exercise.exercise.name.lower() if workout_exercise.exercise else ""

        for set_obj in workout_exercise.sets:
            total_reps += set_obj.reps
            total_volume += set_obj.weight * set_obj.reps
            total_sets += 1

            if any(compound in exercise_name for compound in COMPOUND_EXERCISES):
                compound_sets += 1

    # Get user's current streak and PR count (for streak/PR objectives)
    progress = get_or_create_user_progress(db, user_id)

    dungeons_progressed = []
    dungeons_completed = []
    objectives_completed = []

    for user_dungeon in active_dungeons:
        # Check if expired
        if user_dungeon.expires_at < now:
            user_dungeon.status = DungeonStatus.EXPIRED.value
            continue

        dungeon_progressed = False

        for user_obj in user_dungeon.objectives:
            if user_obj.is_completed:
                continue

            obj_def = user_obj.objective_definition
            old_progress = user_obj.progress
            new_progress = old_progress

            # Calculate progress based on objective type
            if obj_def.objective_type == DungeonObjectiveType.TOTAL_REPS.value:
                new_progress = old_progress + total_reps
            elif obj_def.objective_type == DungeonObjectiveType.TOTAL_VOLUME.value:
                new_progress = old_progress + int(total_volume)
            elif obj_def.objective_type == DungeonObjectiveType.TOTAL_SETS.value:
                new_progress = old_progress + total_sets
            elif obj_def.objective_type == DungeonObjectiveType.COMPOUND_SETS.value:
                new_progress = old_progress + compound_sets
            elif obj_def.objective_type == DungeonObjectiveType.WORKOUT_COUNT.value:
                new_progress = old_progress + 1
            # PR_ACHIEVED and STREAK_MAINTAIN handled separately

            if new_progress != old_progress:
                user_obj.progress = min(new_progress, obj_def.target_value)
                dungeon_progressed = True

                # Check if objective completed
                if user_obj.progress >= obj_def.target_value:
                    user_obj.is_completed = True
                    user_obj.completed_at = now
                    objectives_completed.append(obj_def.name)

        if dungeon_progressed:
            dungeons_progressed.append(user_dungeon.id)

            # Check if all required objectives complete
            required_complete = all(
                obj.is_completed
                for obj in user_dungeon.objectives
                if obj.objective_definition.is_required
            )

            if required_complete and user_dungeon.status != DungeonStatus.COMPLETED.value:
                user_dungeon.status = DungeonStatus.COMPLETED.value
                user_dungeon.completed_at = now
                dungeons_completed.append(user_dungeon.id)

    db.flush()

    return {
        "dungeons_progressed": dungeons_progressed,
        "dungeons_completed": dungeons_completed,
        "objectives_completed": objectives_completed
    }


def claim_dungeon_rewards(db: Session, user_id: str, user_dungeon_id: str) -> Dict[str, Any]:
    """
    Claim XP rewards for a completed dungeon.

    Raises:
        ValueError: If dungeon not found, not completed, or already claimed
    """
    user_dungeon = db.query(UserDungeon).filter(
        UserDungeon.id == user_dungeon_id,
        UserDungeon.user_id == user_id
    ).first()

    if not user_dungeon:
        raise ValueError("Dungeon not found")

    if user_dungeon.status != DungeonStatus.COMPLETED.value:
        raise ValueError("Dungeon not completed yet")

    definition = user_dungeon.definition

    # Calculate base XP
    base_xp = definition.base_xp_reward

    # Calculate stretch bonus
    stretch_bonus_xp = 0
    if user_dungeon.stretch_type == "stretch":
        stretch_bonus_xp = int(base_xp * 0.25)
    elif user_dungeon.stretch_type == "very_stretch":
        stretch_bonus_xp = int(base_xp * 0.50)

    # Calculate bonus objectives XP
    bonus_obj_xp = sum(
        obj.objective_definition.xp_bonus
        for obj in user_dungeon.objectives
        if obj.is_completed and not obj.objective_definition.is_required
    )

    # Total XP
    total_xp = base_xp + stretch_bonus_xp + bonus_obj_xp

    # Award XP
    progress = get_or_create_user_progress(db, user_id)
    old_level = progress.level
    old_rank = progress.rank

    progress.total_xp += total_xp

    # Check for level ups
    while progress.total_xp >= xp_for_level(progress.level + 1):
        progress.level += 1

    # Update rank if needed
    new_rank = get_rank_for_level(progress.level)
    rank_changed = new_rank != old_rank
    if rank_changed:
        progress.rank = new_rank

    # Mark dungeon as claimed
    user_dungeon.status = DungeonStatus.CLAIMED.value
    user_dungeon.claimed_at = datetime.utcnow()
    user_dungeon.xp_earned = base_xp
    user_dungeon.stretch_bonus_xp = stretch_bonus_xp

    db.flush()

    return {
        "success": True,
        "xp_earned": base_xp,
        "stretch_bonus_xp": stretch_bonus_xp,
        "bonus_objectives_xp": bonus_obj_xp,
        "total_xp": progress.total_xp,
        "level": progress.level,
        "leveled_up": progress.level > old_level,
        "new_level": progress.level if progress.level > old_level else None,
        "rank": progress.rank,
        "rank_changed": rank_changed,
        "new_rank": progress.rank if rank_changed else None
    }


def get_dungeon_history(
    db: Session,
    user_id: str,
    skip: int = 0,
    limit: int = 20
) -> Dict[str, Any]:
    """Get past dungeon attempts."""
    now = datetime.utcnow()

    # Get terminal-state dungeons
    dungeons = db.query(UserDungeon).filter(
        UserDungeon.user_id == user_id,
        UserDungeon.status.in_([
            DungeonStatus.CLAIMED.value,
            DungeonStatus.EXPIRED.value,
            DungeonStatus.ABANDONED.value
        ])
    ).order_by(UserDungeon.created_at.desc()).offset(skip).limit(limit).all()

    # Count totals
    total_completed = db.query(UserDungeon).filter(
        UserDungeon.user_id == user_id,
        UserDungeon.status == DungeonStatus.CLAIMED.value
    ).count()

    total_abandoned = db.query(UserDungeon).filter(
        UserDungeon.user_id == user_id,
        UserDungeon.status == DungeonStatus.ABANDONED.value
    ).count()

    total_expired = db.query(UserDungeon).filter(
        UserDungeon.user_id == user_id,
        UserDungeon.status == DungeonStatus.EXPIRED.value
    ).count()

    return {
        "dungeons": [build_dungeon_summary(d, now) for d in dungeons],
        "total_completed": total_completed,
        "total_abandoned": total_abandoned,
        "total_expired": total_expired
    }
