"""
Dungeon Seed Data - Solo Leveling themed dungeon definitions
"""
from sqlalchemy.orm import Session
from datetime import datetime
import uuid

from app.models.dungeon import DungeonDefinition, DungeonObjectiveDefinition


# Dungeon definitions organized by rank
DUNGEON_SEEDS = [
    # ==================== E-RANK DUNGEONS ====================
    {
        "id": "goblin_cave_e",
        "name": "Goblin Cave",
        "description": "A small cave infested with low-rank monsters. Perfect for beginners.",
        "rank": "E",
        "duration_hours": 72,
        "base_xp_reward": 150,
        "min_user_level": 1,
        "max_user_level": 15,
        "spawn_weight": 100,
        "objectives": [
            {"name": "Clear the Cave", "description": "Complete 80 total reps", "type": "total_reps", "target": 80, "required": True},
            {"name": "Defeat the Chief", "description": "Complete 4 sets of compound lifts", "type": "compound_sets", "target": 4, "required": True},
        ]
    },
    {
        "id": "cursed_forest_e",
        "name": "Cursed Forest",
        "description": "Dark trees hide lurking beasts. Stay alert.",
        "rank": "E",
        "duration_hours": 72,
        "base_xp_reward": 175,
        "min_user_level": 1,
        "max_user_level": 15,
        "spawn_weight": 100,
        "objectives": [
            {"name": "Navigate the Woods", "description": "Lift 5,000 lbs total volume", "type": "total_volume", "target": 5000, "required": True},
            {"name": "Purify the Grove", "description": "Complete 2 workouts", "type": "workout_count", "target": 2, "required": True},
        ]
    },
    {
        "id": "skeleton_crypt_e",
        "name": "Skeleton Crypt",
        "description": "An ancient burial ground stirring with restless bones.",
        "rank": "E",
        "duration_hours": 72,
        "base_xp_reward": 150,
        "min_user_level": 1,
        "max_user_level": 15,
        "spawn_weight": 100,
        "objectives": [
            {"name": "Break the Bones", "description": "Complete 100 total reps", "type": "total_reps", "target": 100, "required": True},
            {"name": "Shatter the Skull", "description": "Complete 10 total sets", "type": "total_sets", "target": 10, "required": True},
        ]
    },

    # ==================== D-RANK DUNGEONS ====================
    {
        "id": "wolf_den_d",
        "name": "Wolf Den",
        "description": "A pack of shadow wolves guards this rocky den.",
        "rank": "D",
        "duration_hours": 72,
        "base_xp_reward": 250,
        "min_user_level": 8,
        "max_user_level": 30,
        "spawn_weight": 100,
        "objectives": [
            {"name": "Hunt the Pack", "description": "Complete 2 workouts", "type": "workout_count", "target": 2, "required": True},
            {"name": "Challenge the Alpha", "description": "Complete 8 sets of compound lifts", "type": "compound_sets", "target": 8, "required": True},
            {"name": "Claim the Territory", "description": "Lift 8,000 lbs total", "type": "total_volume", "target": 8000, "required": True},
        ]
    },
    {
        "id": "spider_nest_d",
        "name": "Spider Nest",
        "description": "Webs stretch across every surface. Giant spiders lurk within.",
        "rank": "D",
        "duration_hours": 72,
        "base_xp_reward": 275,
        "min_user_level": 8,
        "max_user_level": 30,
        "spawn_weight": 100,
        "objectives": [
            {"name": "Burn the Webs", "description": "Complete 150 total reps", "type": "total_reps", "target": 150, "required": True},
            {"name": "Slay the Queen", "description": "Complete 6 sets of compound lifts", "type": "compound_sets", "target": 6, "required": True},
            {"name": "Escape Alive", "description": "Complete 2 workouts", "type": "workout_count", "target": 2, "required": True},
        ]
    },
    {
        "id": "haunted_mine_d",
        "name": "Haunted Mine",
        "description": "Abandoned tunnels echo with the moans of fallen miners.",
        "rank": "D",
        "duration_hours": 72,
        "base_xp_reward": 250,
        "min_user_level": 8,
        "max_user_level": 30,
        "spawn_weight": 100,
        "objectives": [
            {"name": "Clear the Shaft", "description": "Complete 120 total reps", "type": "total_reps", "target": 120, "required": True},
            {"name": "Mine the Core", "description": "Lift 10,000 lbs total", "type": "total_volume", "target": 10000, "required": True},
        ]
    },

    # ==================== C-RANK DUNGEONS ====================
    {
        "id": "orc_stronghold_c",
        "name": "Orc Stronghold",
        "description": "A fortified camp of war-hungry orcs. Their war drums echo.",
        "rank": "C",
        "duration_hours": 96,
        "base_xp_reward": 400,
        "min_user_level": 20,
        "max_user_level": 50,
        "spawn_weight": 80,
        "objectives": [
            {"name": "Breach the Gates", "description": "Complete 3 workouts", "type": "workout_count", "target": 3, "required": True},
            {"name": "Crush the Warriors", "description": "Complete 200 total reps", "type": "total_reps", "target": 200, "required": True},
            {"name": "Defeat the Warlord", "description": "Complete 12 sets of compound lifts", "type": "compound_sets", "target": 12, "required": True},
        ]
    },
    {
        "id": "ice_cavern_c",
        "name": "Ice Cavern",
        "description": "Frozen depths where frost giants slumber.",
        "rank": "C",
        "duration_hours": 96,
        "base_xp_reward": 450,
        "min_user_level": 20,
        "max_user_level": 50,
        "spawn_weight": 80,
        "objectives": [
            {"name": "Brave the Cold", "description": "Complete 3 workouts", "type": "workout_count", "target": 3, "required": True},
            {"name": "Shatter the Ice", "description": "Lift 15,000 lbs total", "type": "total_volume", "target": 15000, "required": True},
            {"name": "Awaken the Giant", "description": "Complete 10 sets of compound lifts", "type": "compound_sets", "target": 10, "required": True},
            {"name": "Claim Frozen Treasure", "description": "Set a PR", "type": "pr_achieved", "target": 1, "required": False, "xp_bonus": 100},
        ]
    },
    {
        "id": "demon_shrine_c",
        "name": "Demon Shrine",
        "description": "Dark rituals have left this place corrupted.",
        "rank": "C",
        "duration_hours": 96,
        "base_xp_reward": 425,
        "min_user_level": 20,
        "max_user_level": 50,
        "spawn_weight": 80,
        "objectives": [
            {"name": "Dispel the Darkness", "description": "Complete 250 total reps", "type": "total_reps", "target": 250, "required": True},
            {"name": "Purify the Altar", "description": "Complete 15 sets of compound lifts", "type": "compound_sets", "target": 15, "required": True},
            {"name": "Banish the Summoner", "description": "Complete 3 workouts", "type": "workout_count", "target": 3, "required": True},
        ]
    },

    # ==================== B-RANK DUNGEONS ====================
    {
        "id": "dragon_lair_b",
        "name": "Dragon's Lair",
        "description": "A wyrm guards its hoard deep within the mountain.",
        "rank": "B",
        "duration_hours": 120,
        "base_xp_reward": 650,
        "min_user_level": 35,
        "max_user_level": 75,
        "spawn_weight": 60,
        "objectives": [
            {"name": "Scale the Mountain", "description": "Complete 4 workouts", "type": "workout_count", "target": 4, "required": True},
            {"name": "Face the Flames", "description": "Lift 25,000 lbs total", "type": "total_volume", "target": 25000, "required": True},
            {"name": "Slay the Drake", "description": "Complete 20 sets of compound lifts", "type": "compound_sets", "target": 20, "required": True},
            {"name": "Claim the Hoard", "description": "Set a PR", "type": "pr_achieved", "target": 1, "required": True},
        ]
    },
    {
        "id": "nightmare_realm_b",
        "name": "Nightmare Realm",
        "description": "A twisted dimension where fears become reality.",
        "rank": "B",
        "duration_hours": 120,
        "base_xp_reward": 700,
        "min_user_level": 35,
        "max_user_level": 75,
        "spawn_weight": 60,
        "objectives": [
            {"name": "Enter the Dream", "description": "Complete 4 workouts", "type": "workout_count", "target": 4, "required": True},
            {"name": "Conquer Your Fears", "description": "Complete 300 total reps", "type": "total_reps", "target": 300, "required": True},
            {"name": "Face the Horror", "description": "Complete 18 sets of compound lifts", "type": "compound_sets", "target": 18, "required": True},
            {"name": "Awaken Stronger", "description": "Set a PR", "type": "pr_achieved", "target": 1, "required": False, "xp_bonus": 150},
        ]
    },
    {
        "id": "titan_fortress_b",
        "name": "Titan's Fortress",
        "description": "Ancient giants built this citadel. Their descendants still guard it.",
        "rank": "B",
        "duration_hours": 120,
        "base_xp_reward": 675,
        "min_user_level": 35,
        "max_user_level": 75,
        "spawn_weight": 60,
        "objectives": [
            {"name": "Storm the Gates", "description": "Lift 30,000 lbs total", "type": "total_volume", "target": 30000, "required": True},
            {"name": "Defeat the Guardians", "description": "Complete 25 sets of compound lifts", "type": "compound_sets", "target": 25, "required": True},
            {"name": "Challenge the Titan", "description": "Complete 4 workouts", "type": "workout_count", "target": 4, "required": True},
        ]
    },

    # ==================== A-RANK DUNGEONS ====================
    {
        "id": "abyssal_depths_a",
        "name": "Abyssal Depths",
        "description": "The deepest ocean trench hides horrors beyond imagination.",
        "rank": "A",
        "duration_hours": 144,
        "base_xp_reward": 1000,
        "min_user_level": 55,
        "max_user_level": 95,
        "spawn_weight": 40,
        "objectives": [
            {"name": "Descend into Darkness", "description": "Complete 5 workouts", "type": "workout_count", "target": 5, "required": True},
            {"name": "Crush the Pressure", "description": "Lift 50,000 lbs total", "type": "total_volume", "target": 50000, "required": True},
            {"name": "Battle the Leviathan", "description": "Complete 30 sets of compound lifts", "type": "compound_sets", "target": 30, "required": True},
            {"name": "Claim the Pearl", "description": "Set a PR", "type": "pr_achieved", "target": 1, "required": True},
            {"name": "Survive the Depths", "description": "Complete 400 total reps", "type": "total_reps", "target": 400, "required": False, "xp_bonus": 200},
        ]
    },
    {
        "id": "celestial_temple_a",
        "name": "Celestial Temple",
        "description": "A floating sanctuary where ancient gods once trained warriors.",
        "rank": "A",
        "duration_hours": 144,
        "base_xp_reward": 1100,
        "min_user_level": 55,
        "max_user_level": 95,
        "spawn_weight": 40,
        "objectives": [
            {"name": "Ascend the Steps", "description": "Complete 5 workouts", "type": "workout_count", "target": 5, "required": True},
            {"name": "Pass the Trials", "description": "Complete 35 sets of compound lifts", "type": "compound_sets", "target": 35, "required": True},
            {"name": "Prove Your Worth", "description": "Set 2 PRs", "type": "pr_achieved", "target": 2, "required": True},
            {"name": "Receive the Blessing", "description": "Lift 45,000 lbs total", "type": "total_volume", "target": 45000, "required": True},
        ]
    },

    # ==================== S-RANK DUNGEONS ====================
    {
        "id": "monarchs_domain_s",
        "name": "Monarch's Domain",
        "description": "A realm where only the strongest survive. Face the Shadow Monarch.",
        "rank": "S",
        "duration_hours": 168,
        "base_xp_reward": 1500,
        "min_user_level": 75,
        "is_boss_dungeon": True,
        "spawn_weight": 20,
        "objectives": [
            {"name": "Enter the Void", "description": "Complete 5 workouts", "type": "workout_count", "target": 5, "required": True},
            {"name": "Dominate", "description": "Lift 75,000 lbs total", "type": "total_volume", "target": 75000, "required": True},
            {"name": "Command the Shadows", "description": "Complete 35 sets of compound lifts", "type": "compound_sets", "target": 35, "required": True},
            {"name": "Break All Limits", "description": "Set 2 PRs", "type": "pr_achieved", "target": 2, "required": True},
            {"name": "Unbreakable Will", "description": "Complete 500 total reps", "type": "total_reps", "target": 500, "required": False, "xp_bonus": 300},
        ]
    },
    {
        "id": "architects_tower_s",
        "name": "Architect's Tower",
        "description": "The creator of dungeons resides at the top. Reach him if you dare.",
        "rank": "S",
        "duration_hours": 168,
        "base_xp_reward": 1500,
        "min_user_level": 75,
        "is_boss_dungeon": True,
        "spawn_weight": 20,
        "objectives": [
            {"name": "Ascend the Floors", "description": "Complete 6 workouts", "type": "workout_count", "target": 6, "required": True},
            {"name": "Break the Seals", "description": "Lift 70,000 lbs total", "type": "total_volume", "target": 70000, "required": True},
            {"name": "Pass the Trials", "description": "Complete 40 sets of compound lifts", "type": "compound_sets", "target": 40, "required": True},
            {"name": "Prove Your Strength", "description": "Set 2 PRs", "type": "pr_achieved", "target": 2, "required": True},
        ]
    },

    # ==================== S+ RANK DUNGEONS ====================
    {
        "id": "rulers_gate_s_plus",
        "name": "Ruler's Gate",
        "description": "Beyond this gate lies the domain of the Rulers. Few return.",
        "rank": "S+",
        "duration_hours": 168,
        "base_xp_reward": 2000,
        "min_user_level": 85,
        "is_boss_dungeon": True,
        "spawn_weight": 10,
        "objectives": [
            {"name": "Challenge the Rulers", "description": "Complete 7 workouts", "type": "workout_count", "target": 7, "required": True},
            {"name": "Overwhelming Power", "description": "Lift 100,000 lbs total", "type": "total_volume", "target": 100000, "required": True},
            {"name": "Absolute Dominance", "description": "Complete 50 sets of compound lifts", "type": "compound_sets", "target": 50, "required": True},
            {"name": "Transcend Limits", "description": "Set 3 PRs", "type": "pr_achieved", "target": 3, "required": True},
            {"name": "Unshakeable", "description": "Complete 600 total reps", "type": "total_reps", "target": 600, "required": False, "xp_bonus": 400},
        ]
    },

    # ==================== S++ RANK DUNGEONS ====================
    {
        "id": "absolute_being_gate_s_plus_plus",
        "name": "Absolute Being's Gate",
        "description": "The final trial. Only the Absolute can enter and emerge.",
        "rank": "S++",
        "duration_hours": 168,
        "base_xp_reward": 3000,
        "min_user_level": 95,
        "is_boss_dungeon": True,
        "spawn_weight": 5,
        "objectives": [
            {"name": "Face the Creator", "description": "Complete 7 workouts", "type": "workout_count", "target": 7, "required": True},
            {"name": "Absolute Power", "description": "Lift 150,000 lbs total", "type": "total_volume", "target": 150000, "required": True},
            {"name": "Perfect Execution", "description": "Complete 60 sets of compound lifts", "type": "compound_sets", "target": 60, "required": True},
            {"name": "Shatter Reality", "description": "Set 4 PRs", "type": "pr_achieved", "target": 4, "required": True},
            {"name": "Beyond Mortal", "description": "Complete 750 total reps", "type": "total_reps", "target": 750, "required": False, "xp_bonus": 500},
        ]
    },
]


def seed_dungeon_definitions(db: Session) -> int:
    """
    Seed the database with dungeon definitions.

    Returns:
        Number of dungeons created
    """
    created_count = 0

    for dungeon_data in DUNGEON_SEEDS:
        # Check if dungeon already exists
        existing = db.query(DungeonDefinition).filter(
            DungeonDefinition.id == dungeon_data["id"]
        ).first()

        if existing:
            continue

        # Create dungeon definition
        dungeon = DungeonDefinition(
            id=dungeon_data["id"],
            name=dungeon_data["name"],
            description=dungeon_data["description"],
            rank=dungeon_data["rank"],
            duration_hours=dungeon_data.get("duration_hours", 72),
            base_xp_reward=dungeon_data["base_xp_reward"],
            min_user_level=dungeon_data.get("min_user_level", 1),
            max_user_level=dungeon_data.get("max_user_level"),
            spawn_weight=dungeon_data.get("spawn_weight", 100),
            is_boss_dungeon=dungeon_data.get("is_boss_dungeon", False),
            is_event_dungeon=dungeon_data.get("is_event_dungeon", False),
            is_active=True,
            created_at=datetime.utcnow()
        )
        db.add(dungeon)
        db.flush()

        # Create objectives
        for idx, obj_data in enumerate(dungeon_data.get("objectives", [])):
            objective = DungeonObjectiveDefinition(
                id=f"{dungeon_data['id']}_obj_{idx}",
                dungeon_id=dungeon_data["id"],
                name=obj_data["name"],
                description=obj_data["description"],
                objective_type=obj_data["type"],
                target_value=obj_data["target"],
                is_required=obj_data.get("required", True),
                xp_bonus=obj_data.get("xp_bonus", 0),
                order_index=idx,
                created_at=datetime.utcnow()
            )
            db.add(objective)

        created_count += 1

    db.commit()
    return created_count
