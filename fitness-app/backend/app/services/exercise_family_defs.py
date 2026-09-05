"""Exercise family definitions (ARISE v3 spec §4.2) — pure data, no model imports.

A *family* is the one canonicalization scheme the prescription engine, gates,
load and the coach all key on. The seed already groups exercises by
``canonical_id``; a family is that group plus a curated overlay for the cases
the audit found the substring schemes disagreeing on (big-three matching in
``xp_service``, the keyword map in ``api/analytics``, ``pr_detection``).

This module is imported by the ``v3_exercise_families`` migration, so it must
stay free of SQLAlchemy model imports. Two lookups are exported:

* ``FAMILY_DEFS`` — slug → row for the ``exercise_families`` table.
* ``CANONICAL_NAME_TO_FAMILY`` — canonical exercise name (as seeded by
  ``seed_exercises.py`` and the later exercise migrations) → slug. Cardio,
  sport and "Apple workout" entries are deliberately absent: a NULL family is
  allowed and means "not a loadable lift".
* ``ALIAS_NAME_TO_FAMILY`` — alias name → slug, built from the seed's alias
  lists. Aliases normally inherit through ``canonical_id``; the alias map
  exists so custom exercises can be name-matched and so a handful of aliases
  can be split *out* of their canonical group (``Dumbbell Shrugs`` is an alias
  of ``Shrugs`` in the seed but is its own family here).

Grouping rules (deviating from the spec's §10 aside on purpose): ``front_squat``,
``goblet_squat``, ``hack_squat`` and ``bulgarian_split_squat`` stay separate from
``back_squat`` — merging them would corrupt the back-squat prescription anchor.
Likewise incline/decline/dumbbell benches are not ``bench_press``.

``increment_lb`` is the default progression step: 5 for barbell / machine /
cable / bodyweight families, 2.5 for dumbbell families. ``standards_key``
aligns with the keys of ``api/analytics.STRENGTH_STANDARDS`` (null when no
standard exists for the movement).
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Dict, Iterable, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Family table rows: slug -> (display_name, primary_muscle, is_big_three,
#                             standards_key, increment_lb)
# ---------------------------------------------------------------------------
_F: List[Tuple[str, str, str, bool, Optional[str], float]] = [
    # ── Big three ──
    ("back_squat", "Back Squat", "Quads", True, "squat", 5.0),
    ("bench_press", "Bench Press", "Chest", True, "bench", 5.0),
    ("deadlift", "Deadlift", "Back", True, "deadlift", 5.0),
    # ── Pressing ──
    ("incline_bench_press", "Incline Bench Press", "Upper Chest", False, "incline_bench", 5.0),
    ("decline_bench_press", "Decline Bench Press", "Lower Chest", False, "bench", 5.0),
    ("db_bench_press", "Dumbbell Bench Press", "Chest", False, "bench", 2.5),
    ("incline_db_bench_press", "Incline Dumbbell Bench Press", "Upper Chest", False, "incline_bench", 2.5),
    ("close_grip_bench", "Close-Grip Bench Press", "Triceps", False, "bench", 5.0),
    ("floor_press", "Floor Press", "Chest", False, "bench", 5.0),
    ("machine_chest_press", "Machine Chest Press", "Chest", False, "bench", 5.0),
    ("smith_machine_bench_press", "Smith Machine Bench Press", "Chest", False, "bench", 5.0),
    ("overhead_press", "Overhead Press", "Shoulders", False, "overhead_press", 5.0),
    ("db_shoulder_press", "Dumbbell Shoulder Press", "Shoulders", False, "overhead_press", 2.5),
    ("arnold_press", "Arnold Press", "Shoulders", False, "overhead_press", 2.5),
    ("machine_shoulder_press", "Machine Shoulder Press", "Shoulders", False, "overhead_press", 5.0),
    ("smith_machine_shoulder_press", "Smith Machine Shoulder Press", "Shoulders", False, "overhead_press", 5.0),
    ("push_press", "Push Press", "Shoulders", False, None, 5.0),
    ("landmine_press", "Landmine Press", "Shoulders", False, None, 5.0),
    ("push_up", "Push-up", "Chest", False, None, 5.0),
    ("dip", "Dip", "Triceps", False, "dip", 5.0),
    # ── Chest isolation / delts ──
    ("db_fly", "Dumbbell Fly", "Chest", False, "fly", 2.5),
    ("cable_fly", "Cable Fly", "Chest", False, "fly", 5.0),
    ("incline_cable_fly", "Incline Cable Fly", "Upper Chest", False, "fly", 5.0),
    ("cable_crossover", "Cable Crossover", "Chest", False, "fly", 5.0),
    ("pec_deck", "Pec Deck", "Chest", False, "fly", 5.0),
    ("reverse_pec_deck", "Reverse Pec Deck", "Rear Delts", False, None, 5.0),
    ("db_pullover", "Dumbbell Pullover", "Chest", False, None, 2.5),
    ("lateral_raise", "Lateral Raise", "Side Delts", False, "lateral_raise", 2.5),
    ("cable_lateral_raise", "Cable Lateral Raise", "Side Delts", False, "lateral_raise", 5.0),
    ("front_raise", "Front Raise", "Front Delts", False, None, 2.5),
    ("rear_delt_fly", "Rear Delt Fly", "Rear Delts", False, "fly", 2.5),
    ("face_pull", "Face Pull", "Rear Delts", False, "face_pull", 5.0),
    ("upright_row", "Upright Row", "Traps", False, None, 5.0),
    # ── Triceps ──
    ("tricep_pushdown", "Tricep Pushdown", "Triceps", False, "tricep_extension", 5.0),
    ("overhead_tricep_extension", "Overhead Tricep Extension", "Triceps", False, "tricep_extension", 5.0),
    ("lying_tricep_extension", "Lying Tricep Extension", "Triceps", False, "tricep_extension", 5.0),
    ("tricep_kickback", "Tricep Kickback", "Triceps", False, "tricep_extension", 2.5),
    # ── Deadlift variants / posterior chain ──
    ("sumo_deadlift", "Sumo Deadlift", "Back", False, "deadlift", 5.0),
    ("trap_bar_deadlift", "Trap Bar Deadlift", "Back", False, "deadlift", 5.0),
    ("deficit_deadlift", "Deficit Deadlift", "Back", False, "deadlift", 5.0),
    ("rack_pull", "Rack Pull", "Back", False, "deadlift", 5.0),
    ("romanian_deadlift", "Romanian Deadlift", "Hamstrings", False, "romanian_deadlift", 5.0),
    ("single_leg_rdl", "Single Leg Romanian Deadlift", "Hamstrings", False, "romanian_deadlift", 2.5),
    ("good_morning", "Good Morning", "Hamstrings", False, None, 5.0),
    ("back_extension", "Back Extension", "Lower Back", False, None, 5.0),
    ("glute_ham_raise", "Glute Ham Raise", "Hamstrings", False, None, 5.0),
    ("nordic_curl", "Nordic Hamstring Curl", "Hamstrings", False, None, 5.0),
    ("cable_pull_through", "Cable Pull-Through", "Glutes", False, None, 5.0),
    ("kettlebell_swing", "Kettlebell Swing", "Glutes", False, None, 5.0),
    ("hip_thrust", "Hip Thrust", "Glutes", False, "hip_thrust", 5.0),
    ("single_leg_hip_thrust", "Single-Leg Hip Thrust", "Glutes", False, "hip_thrust", 5.0),
    ("cable_glute_kickback", "Cable Glute Kickback", "Glutes", False, None, 5.0),
    # ── Vertical / horizontal pulls ──
    ("pull_up", "Pull-up", "Lats", False, "pullup", 5.0),
    ("lat_pulldown", "Lat Pulldown", "Lats", False, "lat_pulldown", 5.0),
    ("straight_arm_pulldown", "Straight Arm Pulldown", "Lats", False, "lat_pulldown", 5.0),
    ("barbell_row", "Barbell Row", "Back", False, "row", 5.0),
    ("db_row", "Dumbbell Row", "Back", False, "row", 2.5),
    ("t_bar_row", "T-Bar Row", "Back", False, "row", 5.0),
    ("cable_row", "Seated Cable Row", "Back", False, "row", 5.0),
    ("machine_row", "Machine Row", "Back", False, "row", 5.0),
    ("chest_supported_row", "Chest Supported Row", "Back", False, "row", 5.0),
    ("meadows_row", "Meadows Row", "Back", False, "row", 5.0),
    ("seal_row", "Seal Row", "Back", False, "row", 5.0),
    ("db_high_pull", "Dumbbell High Pull", "Traps", False, None, 2.5),
    ("barbell_shrug", "Shrug", "Traps", False, None, 5.0),
    ("db_shrug", "Dumbbell Shrug", "Traps", False, None, 2.5),
    ("farmers_walk", "Farmer's Walk", "Forearms", False, None, 5.0),
    # ── Biceps / forearms ──
    ("barbell_curl", "Barbell Curl", "Biceps", False, "curl", 5.0),
    ("ez_bar_curl", "EZ Bar Curl", "Biceps", False, "curl", 5.0),
    ("db_curl", "Dumbbell Curl", "Biceps", False, "curl", 2.5),
    ("incline_db_curl", "Incline Dumbbell Curl", "Biceps", False, "curl", 2.5),
    ("hammer_curl", "Hammer Curl", "Biceps", False, "curl", 2.5),
    ("cable_hammer_curl", "Cable Hammer Curl", "Biceps", False, "curl", 5.0),
    # The owner's preacher work is the one-arm dumbbell version, so the
    # family steps in dumbbell increments even though an EZ bar is possible.
    ("preacher_curl", "Preacher Curl", "Biceps", False, "curl", 2.5),
    ("concentration_curl", "Concentration Curl", "Biceps", False, "curl", 2.5),
    ("spider_curl", "Spider Curl", "Biceps", False, "curl", 2.5),
    ("cable_curl", "Cable Curl", "Biceps", False, "curl", 5.0),
    ("reverse_curl", "Reverse Curl", "Forearms", False, "curl", 5.0),
    ("wrist_curl", "Wrist Curl", "Forearms", False, None, 2.5),
    ("reverse_wrist_curl", "Reverse Wrist Curl", "Forearms", False, None, 2.5),
    # ── One-arm variants that the seed tracks separately ──
    ("one_arm_dumbbell_curl", "One-Arm Dumbbell Curl", "Biceps", False, "curl", 2.5),
    ("one_arm_hammer_curl", "One-Arm Hammer Curl", "Biceps", False, "curl", 2.5),
    ("one_arm_cable_curl", "One-Arm Cable Curl", "Biceps", False, "curl", 5.0),
    ("one_arm_lateral_raise", "One-Arm Lateral Raise", "Side Delts", False, "lateral_raise", 2.5),
    ("one_arm_front_raise", "One-Arm Front Raise", "Front Delts", False, None, 2.5),
    ("one_arm_rear_delt_fly", "One-Arm Rear Delt Fly", "Rear Delts", False, "fly", 2.5),
    ("one_arm_dumbbell_press", "One-Arm Dumbbell Press", "Shoulders", False, "overhead_press", 2.5),
    ("one_arm_tricep_pushdown", "One-Arm Tricep Pushdown", "Triceps", False, "tricep_extension", 5.0),
    ("one_arm_overhead_extension", "One-Arm Overhead Extension", "Triceps", False, "tricep_extension", 2.5),
    # ── Squat variants / quads ──
    ("front_squat", "Front Squat", "Quads", False, "squat", 5.0),
    ("goblet_squat", "Goblet Squat", "Quads", False, "squat", 2.5),
    ("hack_squat", "Hack Squat", "Quads", False, "squat", 5.0),
    ("bulgarian_split_squat", "Bulgarian Split Squat", "Quads", False, "squat", 2.5),
    ("smith_machine_squat", "Smith Machine Squat", "Quads", False, "squat", 5.0),
    ("box_squat", "Box Squat", "Quads", False, "squat", 5.0),
    ("safety_bar_squat", "Safety Bar Squat", "Quads", False, "squat", 5.0),
    ("pause_squat", "Pause Squat", "Quads", False, "squat", 5.0),
    ("belt_squat", "Belt Squat", "Quads", False, None, 5.0),
    ("sissy_squat", "Sissy Squat", "Quads", False, None, 5.0),
    ("pistol_squat", "Pistol Squat", "Quads", False, None, 5.0),
    ("cossack_squat", "Cossack Squat", "Quads", False, None, 5.0),
    ("leg_press", "Leg Press", "Quads", False, "leg_press", 5.0),
    ("leg_extension", "Leg Extension", "Quads", False, "leg_extension", 5.0),
    ("leg_curl", "Leg Curl", "Hamstrings", False, "leg_curl", 5.0),
    ("lying_leg_curl", "Lying Leg Curl", "Hamstrings", False, "leg_curl", 5.0),
    ("seated_leg_curl", "Seated Leg Curl", "Hamstrings", False, "leg_curl", 5.0),
    ("lunge", "Lunge", "Quads", False, None, 2.5),
    ("curtsy_lunge", "Curtsy Lunge", "Glutes", False, None, 2.5),
    ("step_up", "Step-up", "Quads", False, None, 2.5),
    ("hip_abductor", "Hip Abductor", "Glutes", False, None, 5.0),
    ("hip_adductor", "Hip Adductor", "Adductors", False, None, 5.0),
    ("standing_calf_raise", "Standing Calf Raise", "Calves", False, "calf_raise", 5.0),
    ("seated_calf_raise", "Seated Calf Raise", "Calves", False, "calf_raise", 5.0),
    ("leg_press_calf_raise", "Leg Press Calf Raise", "Calves", False, "calf_raise", 5.0),
    ("donkey_calf_raise", "Donkey Calf Raise", "Calves", False, "calf_raise", 5.0),
    ("box_jump", "Box Jump", "Quads", False, None, 5.0),
    ("sled_push", "Sled Push", "Quads", False, None, 5.0),
    ("wall_sit", "Wall Sit", "Quads", False, None, 5.0),
    ("wall_ball", "Wall Ball", "Quads", False, None, 5.0),
    # ── Core ──
    ("plank", "Plank", "Core", False, None, 5.0),
    ("side_plank", "Side Plank", "Obliques", False, None, 5.0),
    ("crunch", "Crunch", "Abs", False, None, 5.0),
    ("cable_crunch", "Cable Crunch", "Abs", False, None, 5.0),
    ("bicycle_crunch", "Bicycle Crunch", "Abs", False, None, 5.0),
    ("reverse_crunch", "Reverse Crunch", "Lower Abs", False, None, 5.0),
    ("sit_up", "Sit-up", "Abs", False, None, 5.0),
    ("decline_sit_up", "Decline Sit-up", "Abs", False, None, 5.0),
    ("medicine_ball_sit_up", "Medicine Ball Sit-up", "Abs", False, None, 5.0),
    ("v_up", "V-up", "Abs", False, None, 5.0),
    ("russian_twist", "Russian Twist", "Obliques", False, None, 5.0),
    ("medicine_ball_rotation", "Medicine Ball Rotation", "Obliques", False, None, 5.0),
    ("woodchopper", "Woodchopper", "Obliques", False, None, 5.0),
    ("pallof_press", "Pallof Press", "Core", False, None, 5.0),
    ("hanging_leg_raise", "Hanging Leg Raise", "Lower Abs", False, None, 5.0),
    ("hanging_knee_raise", "Hanging Knee Raise", "Lower Abs", False, None, 5.0),
    ("toes_to_bar", "Toes to Bar", "Lower Abs", False, None, 5.0),
    ("flutter_kick", "Flutter Kick", "Lower Abs", False, None, 5.0),
    ("ab_wheel_rollout", "Ab Wheel Rollout", "Core", False, None, 5.0),
    ("barbell_rollout", "Barbell Rollout", "Core", False, None, 5.0),
    ("stability_ball_rollout", "Stability Ball Rollout", "Core", False, None, 5.0),
    ("dead_bug", "Dead Bug", "Core", False, None, 5.0),
    ("bird_dog", "Bird Dog", "Core", False, None, 5.0),
    ("hollow_hold", "Hollow Hold", "Core", False, None, 5.0),
    ("mountain_climber", "Mountain Climber", "Core", False, None, 5.0),
    ("turkish_get_up", "Turkish Get-up", "Core", False, None, 5.0),
    ("medicine_ball_slam", "Medicine Ball Slam", "Core", False, None, 5.0),
    ("medicine_ball_chest_pass", "Medicine Ball Chest Pass", "Chest", False, None, 5.0),
    ("medicine_ball_overhead_throw", "Medicine Ball Overhead Throw", "Core", False, None, 5.0),
]

FAMILY_DEFS: Dict[str, Dict[str, object]] = {
    slug: {
        "display_name": display,
        "primary_muscle": muscle,
        "is_big_three": big3,
        "standards_key": standards,
        "increment_lb": increment,
    }
    for slug, display, muscle, big3, standards, increment in _F
}

BIG_THREE_FAMILIES: Tuple[str, ...] = tuple(
    slug for slug, defn in FAMILY_DEFS.items() if defn["is_big_three"]
)

# ---------------------------------------------------------------------------
# Canonical seed name -> family slug. Every loadable canonical in
# seed_exercises.py (plus the canonicals the later exercise migrations added)
# appears here; cardio / sport / Apple-workout entries are deliberately absent.
# ---------------------------------------------------------------------------
CANONICAL_NAME_TO_FAMILY: Dict[str, str] = {
    # Push
    "Barbell Bench Press": "bench_press",
    "Incline Barbell Bench Press": "incline_bench_press",
    "Decline Barbell Bench Press": "decline_bench_press",
    "Dumbbell Bench Press": "db_bench_press",
    "Incline Dumbbell Bench Press": "incline_db_bench_press",
    "Dumbbell Flyes": "db_fly",
    "Cable Flyes": "cable_fly",
    "Push-ups": "push_up",
    "Overhead Press": "overhead_press",
    "Seated Dumbbell Press": "db_shoulder_press",
    "Arnold Press": "arnold_press",
    "Lateral Raises": "lateral_raise",
    "Front Raises": "front_raise",
    "Rear Delt Flyes": "rear_delt_fly",
    "Close-Grip Bench Press": "close_grip_bench",
    "Tricep Dips": "dip",
    "Tricep Pushdowns": "tricep_pushdown",
    "Overhead Tricep Extension": "overhead_tricep_extension",
    # Pull
    "Barbell Deadlift": "deadlift",
    "Sumo Deadlift": "sumo_deadlift",
    "Romanian Deadlift": "romanian_deadlift",
    "Single Leg Romanian Deadlift": "single_leg_rdl",
    "Pull-ups": "pull_up",
    "Lat Pulldown": "lat_pulldown",
    "Straight Arm Pulldown": "straight_arm_pulldown",
    "Dumbbell High Pull": "db_high_pull",
    "Barbell Row": "barbell_row",
    "Dumbbell Row": "db_row",
    "T-Bar Row": "t_bar_row",
    "Seated Cable Row": "cable_row",
    "Face Pulls": "face_pull",
    "Barbell Curl": "barbell_curl",
    "Dumbbell Curl": "db_curl",
    "Hammer Curl": "hammer_curl",
    "Preacher Curl": "preacher_curl",
    "Cable Curl": "cable_curl",
    # Legs
    "Barbell Back Squat": "back_squat",
    "Front Squat": "front_squat",
    "Goblet Squat": "goblet_squat",
    "Bulgarian Split Squat": "bulgarian_split_squat",
    "Leg Press": "leg_press",
    "Hack Squat": "hack_squat",
    "Leg Extension": "leg_extension",
    "Leg Curl": "leg_curl",
    "Walking Lunges": "lunge",
    "Hip Thrust": "hip_thrust",
    "Standing Calf Raise": "standing_calf_raise",
    "Seated Calf Raise": "seated_calf_raise",
    # Core
    "Plank": "plank",
    "Side Plank": "side_plank",
    "Crunches": "crunch",
    "Russian Twists": "russian_twist",
    "Hanging Leg Raise": "hanging_leg_raise",
    "Ab Wheel Rollout": "ab_wheel_rollout",
    "Cable Crunches": "cable_crunch",
    # Accessories
    "Shrugs": "barbell_shrug",
    "Farmer's Walk": "farmers_walk",
    "Wrist Curls": "wrist_curl",
    # One-arm variants (the owner logs One-Arm Preacher Curl as *the* preacher
    # movement, so it folds into preacher_curl; the rest stay separate)
    "One-Arm Preacher Curl": "preacher_curl",
    "One-Arm Dumbbell Curl": "one_arm_dumbbell_curl",
    "One-Arm Hammer Curl": "one_arm_hammer_curl",
    "One-Arm Cable Curl": "one_arm_cable_curl",
    "One-Arm Lateral Raise": "one_arm_lateral_raise",
    "One-Arm Front Raise": "one_arm_front_raise",
    "One-Arm Rear Delt Fly": "one_arm_rear_delt_fly",
    "One-Arm Dumbbell Press": "one_arm_dumbbell_press",
    "One-Arm Tricep Pushdown": "one_arm_tricep_pushdown",
    "One-Arm Overhead Extension": "one_arm_overhead_extension",
    # Machines
    "Machine Chest Press": "machine_chest_press",
    "Pec Deck": "pec_deck",
    "Machine Shoulder Press": "machine_shoulder_press",
    "Smith Machine Bench Press": "smith_machine_bench_press",
    "Smith Machine Squat": "smith_machine_squat",
    "Cable Crossover": "cable_crossover",
    "Machine Row": "machine_row",
    "Chest Supported Row": "chest_supported_row",
    "Reverse Pec Deck": "reverse_pec_deck",
    "Cable Lateral Raise": "cable_lateral_raise",
    "Machine Hip Abductor": "hip_abductor",
    "Machine Hip Adductor": "hip_adductor",
    # Additional core
    "Medicine Ball Rotations": "medicine_ball_rotation",
    "Bicycle Crunches": "bicycle_crunch",
    "Dead Bug": "dead_bug",
    "Mountain Climbers": "mountain_climber",
    "Pallof Press": "pallof_press",
    "Decline Sit-ups": "decline_sit_up",
    "V-ups": "v_up",
    "Woodchoppers": "woodchopper",
    # Additional strength variations
    "Lying Tricep Extension": "lying_tricep_extension",
    # `add_expanded_exercises` seeded this group with Skull Crushers as the
    # canonical row; the seed and `lying_tricep_aliases` name it the other way.
    "Skull Crushers": "lying_tricep_extension",
    "EZ Bar Curl": "ez_bar_curl",
    "Concentration Curl": "concentration_curl",
    "Incline Dumbbell Curl": "incline_db_curl",
    "Spider Curl": "spider_curl",
    "Tricep Kickbacks": "tricep_kickback",
    "Trap Bar Deadlift": "trap_bar_deadlift",
    "Good Mornings": "good_morning",
    "Step-ups": "step_up",
    "Rack Pull": "rack_pull",
    # Restored variations
    "Seated Barbell Shoulder Press": "overhead_press",
    "Smith Machine Shoulder Press": "smith_machine_shoulder_press",
    "Push Press": "push_press",
    "Landmine Press": "landmine_press",
    "Box Squat": "box_squat",
    "Safety Bar Squat": "safety_bar_squat",
    "Pause Squat": "pause_squat",
    "Sissy Squat": "sissy_squat",
    "Belt Squat": "belt_squat",
    "Deficit Deadlift": "deficit_deadlift",
    "Reverse Lunge": "lunge",
    "Curtsy Lunge": "curtsy_lunge",
    "Cossack Squat": "cossack_squat",
    "Single-Leg Hip Thrust": "single_leg_hip_thrust",
    "Lying Leg Curl": "lying_leg_curl",
    "Seated Leg Curl": "seated_leg_curl",
    "Nordic Hamstring Curl": "nordic_curl",
    "Glute Ham Raise": "glute_ham_raise",
    "Cable Pull-Through": "cable_pull_through",
    "Back Extension": "back_extension",
    "Kettlebell Swing": "kettlebell_swing",
    "Cable Glute Kickback": "cable_glute_kickback",
    "Pendlay Row": "barbell_row",
    "Meadows Row": "meadows_row",
    "Seal Row": "seal_row",
    "Floor Press": "floor_press",
    "Dumbbell Pullover": "db_pullover",
    "Reverse Curl": "reverse_curl",
    "Cable Hammer Curl": "cable_hammer_curl",
    "Leg Press Calf Raise": "leg_press_calf_raise",
    "Donkey Calf Raise": "donkey_calf_raise",
    "Upright Row": "upright_row",
    "Reverse Wrist Curl": "reverse_wrist_curl",
    "Incline Cable Fly": "incline_cable_fly",
    "Pistol Squat": "pistol_squat",
    "Sit-ups": "sit_up",
    "Medicine Ball Slam": "medicine_ball_slam",
    "Wall Ball": "wall_ball",
    "Medicine Ball Chest Pass": "medicine_ball_chest_pass",
    "Medicine Ball Overhead Throw": "medicine_ball_overhead_throw",
    "Medicine Ball Sit-up": "medicine_ball_sit_up",
    "Barbell Rollout": "barbell_rollout",
    "Stability Ball Rollout": "stability_ball_rollout",
    "Reverse Crunch": "reverse_crunch",
    "Flutter Kicks": "flutter_kick",
    "Hollow Hold": "hollow_hold",
    "Bird Dog": "bird_dog",
    "Toes to Bar": "toes_to_bar",
    "Hanging Knee Raise": "hanging_knee_raise",
    "Box Jump": "box_jump",
    "Sled Push": "sled_push",
    "Turkish Get-up": "turkish_get_up",
    "Wall Sit": "wall_sit",
}

# Alias name -> family slug. Mirrors the seed's alias lists (kept in sync by
# tests/test_exercise_families.py) plus a few common free-text spellings for
# custom-exercise name matching. Aliases that are split out of their
# canonical group (Dumbbell Shrugs) are listed with their own family.
_ALIASES: Dict[str, Tuple[str, ...]] = {
    "bench_press": ("Bench Press", "BB Bench", "Flat Bench", "Flat Barbell Bench Press", "Barbell Bench"),
    "incline_bench_press": ("Incline Bench", "Incline BB Bench", "Incline Bench Press", "Incline Barbell Bench"),
    "decline_bench_press": ("Decline Bench", "Decline Bench Press"),
    "db_bench_press": ("DB Bench", "Dumbbell Bench", "Dumbbell Press", "Flat Dumbbell Bench Press"),
    "incline_db_bench_press": ("Incline DB Bench", "Incline Dumbbell Press", "Incline DB Press"),
    "db_fly": ("DB Flyes", "Chest Flyes", "Dumbbell Fly", "Dumbbell Flys", "Chest Fly"),
    "cable_fly": ("Cable Chest Flyes", "Cable Fly", "Cable Flys"),
    "push_up": ("Pushups", "Press-ups", "Push Ups", "Push-up", "Pushup"),
    "overhead_press": (
        "OHP", "Military Press", "Shoulder Press", "Barbell Overhead Press", "Standing Overhead Press",
        "Barbell Shoulder Press", "Standing Barbell Press", "Seated Barbell Press", "Seated Military Press",
        "Seated BB Shoulder Press", "Seated Overhead Press",
    ),
    "db_shoulder_press": ("Seated DB Press", "Seated Shoulder Press", "Dumbbell Shoulder Press", "DB Shoulder Press", "Dumbbell Overhead Press"),
    "arnold_press": ("Arnold Shoulder Press",),
    "lateral_raise": ("Side Raises", "DB Lateral Raises", "Lateral Shoulder Raise", "Lateral Raise", "Side Raise", "Dumbbell Lateral Raise", "Side Lateral Raise"),
    "front_raise": ("Front Delt Raises", "Front Raise", "Front Delt Raise", "Dumbbell Front Raise"),
    "rear_delt_fly": ("Reverse Flyes", "Rear Delts", "Rear Delt Fly", "Reverse Fly", "Rear Delt Raise"),
    "close_grip_bench": ("CG Bench", "Close Grip Bench", "Close Grip Bench Press"),
    "dip": ("Dips", "Triceps Dips", "Chest Dip", "Dip", "Weighted Dips", "Bench Dips"),
    "tricep_pushdown": ("Cable Pushdowns", "Triceps Pushdowns", "Triceps Pulldown", "Tricep Pushdown", "Rope Pushdown", "Cable Pushdown", "Pushdowns"),
    "overhead_tricep_extension": ("Tricep Extensions", "Overhead Extension", "Overhead Triceps Extension", "Tricep Extension"),
    "deadlift": ("Deadlift", "Conventional Deadlift", "Deadlifts", "BB Deadlift"),
    "sumo_deadlift": ("Sumo DL", "Sumo Deadlifts"),
    "romanian_deadlift": ("RDL", "Stiff-Leg Deadlift", "Romanian Deadlifts", "RDLs", "Stiff Leg Deadlift"),
    "single_leg_rdl": ("Single Leg RDL", "SL RDL", "One Leg RDL", "Single-Leg RDL"),
    "pull_up": ("Pullups", "Chin-ups", "Pull-Up", "Pull Ups", "Pullup", "Chin Ups", "Chinups", "Weighted Pull-ups"),
    "lat_pulldown": ("Lat Pulldowns", "Lat Pull Down", "Lat Pull Downs", "Pulldown", "Pulldowns", "Cable Pulldown"),
    "straight_arm_pulldown": ("Straight Arm Pull Down", "Straight Arm Lat Pulldown"),
    "db_high_pull": ("High Pull", "DB High Pull"),
    "barbell_row": ("BB Row", "Bent-Over Row", "Bent Over Row", "Barbell Rows", "Bent Over Barbell Row", "Pendlay Rows", "Dead-Stop Row"),
    "db_row": ("DB Row", "One-Arm Row", "Dumbbell Rows", "One Arm Dumbbell Row", "Single Arm Row"),
    "t_bar_row": ("T Bar Row", "T-Bar Rows"),
    "cable_row": ("Cable Row", "Seated Row", "Seated Cable Rows", "Cable Rows"),
    "face_pull": ("Cable Face Pulls", "Face Pull", "Cable Face Pull"),
    "barbell_curl": ("BB Curl", "Bicep Curl", "Barbell Curls", "Barbell Bicep Curl"),
    "db_curl": ("DB Curl", "Dumbbell Curls", "Dumbbell Bicep Curl", "DB Curls"),
    "hammer_curl": ("Hammer Curls", "Dumbbell Hammer Curl"),
    "preacher_curl": ("Preacher Curls", "Single Arm Preacher Curl", "1-Arm Preacher Curl", "Dumbbell Preacher Curl"),
    "cable_curl": ("Cable Bicep Curl", "Cable Curls"),
    "back_squat": ("Squat", "Back Squat", "BB Squat", "Barbell Squat", "Squats", "Back Squats", "High Bar Squat", "Low Bar Squat"),
    "front_squat": ("Front Squats", "Barbell Front Squat"),
    "goblet_squat": ("Goblet Squats",),
    "bulgarian_split_squat": ("Split Squat", "Bulgarian Squat", "Bulgarian Split Squats", "Rear Foot Elevated Split Squat"),
    "leg_press": ("Leg Press Machine", "Leg Presses"),
    "hack_squat": ("Hack Squat Machine", "Hack Squats"),
    "leg_extension": ("Leg Extensions", "Quad Extension", "Quad Extensions"),
    "leg_curl": ("Leg Curls", "Hamstring Curl", "Hamstring Curls", "Ham Curl"),
    "lunge": ("Lunges", "Alternating Lunge", "Walking Lunge", "Reverse Lunges", "Barbell Reverse Lunge", "Dumbbell Reverse Lunge", "Forward Lunge", "Forward Lunges", "Dumbbell Lunges", "Lunge"),
    "hip_thrust": ("Barbell Hip Thrust", "Glute Bridge", "Hip Thrusts"),
    "standing_calf_raise": ("Calf Raises", "Calf Raise", "Standing Calf Raises"),
    "seated_calf_raise": ("Seated Calf Raises",),
    "plank": ("Front Plank", "Planks"),
    "side_plank": ("Side Planks",),
    "crunch": ("Crunch", "Ab Crunch", "Ab Crunches"),
    "russian_twist": ("Russian Twist",),
    "hanging_leg_raise": ("Leg Raises", "Hanging Leg Raises", "Leg Raise"),
    "ab_wheel_rollout": ("Ab Wheel", "Rollouts", "Ab Rollout"),
    "cable_crunch": ("Cable Crunch",),
    "barbell_shrug": ("Barbell Shrugs", "Shrug", "BB Shrugs", "Barbell Shrug"),
    "db_shrug": ("Dumbbell Shrugs", "DB Shrugs", "Dumbbell Shrug", "DB Shrug"),
    "farmers_walk": ("Farmers Walk", "Farmer Carry", "Farmer's Carry", "Farmers Carry"),
    "wrist_curl": ("Wrist Curl",),
    "one_arm_dumbbell_curl": ("Single Arm Dumbbell Curl", "1-Arm Curl", "Single Arm Curl"),
    "one_arm_hammer_curl": ("Single Arm Hammer Curl", "1-Arm Hammer Curl"),
    "one_arm_cable_curl": ("Single Arm Cable Curl", "1-Arm Cable Curl"),
    "one_arm_lateral_raise": ("Single Arm Lateral Raise", "1-Arm Lateral Raise"),
    "one_arm_front_raise": ("Single Arm Front Raise", "1-Arm Front Raise"),
    "one_arm_rear_delt_fly": ("Single Arm Rear Delt Fly", "1-Arm Reverse Fly"),
    "one_arm_dumbbell_press": ("Single Arm Shoulder Press", "1-Arm Dumbbell Press", "Single Arm Dumbbell Press"),
    "one_arm_tricep_pushdown": ("Single Arm Tricep Pushdown", "1-Arm Pushdown"),
    "one_arm_overhead_extension": ("Single Arm Overhead Extension", "1-Arm Tricep Extension"),
    "machine_chest_press": ("Chest Press Machine", "Seated Chest Press", "Chest Press"),
    "pec_deck": ("Machine Fly", "Pec Deck Machine", "Machine Flye", "Pec Fly", "Pec Deck Fly"),
    "machine_shoulder_press": ("Shoulder Press Machine", "Seated Machine Press", "Machine Press"),
    "smith_machine_bench_press": ("Smith Bench", "Smith Bench Press", "Smith Machine Bench"),
    "smith_machine_squat": ("Smith Squat", "Smith Machine Squats"),
    "cable_crossover": ("Cable Crossovers", "Cable Cross"),
    "machine_row": ("Seated Machine Row", "Machine Back Row", "Machine Rows", "Seated Machine Rows"),
    "chest_supported_row": ("Chest Supported DB Row", "Incline Row", "Chest-Supported Row"),
    "reverse_pec_deck": ("Reverse Machine Fly", "Machine Reverse Fly"),
    "cable_lateral_raise": ("Cable Side Raise", "Cable Lat Raise"),
    "hip_abductor": ("Hip Abductor", "Abductor Machine", "Hip Abduction"),
    "hip_adductor": ("Hip Adductor", "Adductor Machine", "Hip Adduction"),
    "medicine_ball_rotation": ("Med Ball Rotations", "Medicine Ball Twist"),
    "bicycle_crunch": ("Bicycle Crunch",),
    "dead_bug": ("Dead Bugs",),
    "mountain_climber": ("Mountain Climber",),
    "pallof_press": ("Pallof Press Hold", "Anti-Rotation Press"),
    "decline_sit_up": ("Decline Sit-up", "Decline Situps"),
    "v_up": ("V-up", "V Ups"),
    "woodchopper": ("Cable Woodchop", "Wood Chop", "Woodchop"),
    "lying_tricep_extension": ("Skull Crushers", "Skull Crusher", "EZ Bar Skull Crusher", "Lying Triceps Extension", "Lying Tricep Extensions", "Skullcrushers"),
    "ez_bar_curl": ("EZ Curl", "EZ Barbell Curl", "EZ Bar Curls"),
    "concentration_curl": ("Concentration Curls", "Seated Concentration Curl"),
    "incline_db_curl": ("Incline DB Curl", "Incline Curl", "Incline Dumbbell Curls", "Incline Curls"),
    "spider_curl": ("Spider Curls",),
    "tricep_kickback": ("Kickbacks", "DB Kickbacks", "Dumbbell Kickback", "Tricep Kickback"),
    "trap_bar_deadlift": ("Hex Bar Deadlift", "Trap Bar DL"),
    "good_morning": ("Good Morning", "Barbell Good Morning"),
    "step_up": ("Step Up", "Dumbbell Step-up", "Barbell Step-up", "Step Ups", "Step-up"),
    "rack_pull": ("Rack Pulls", "Block Pull"),
    "smith_machine_shoulder_press": ("Smith Shoulder Press", "Smith Machine Overhead Press"),
    "push_press": ("Barbell Push Press", "Overhead Push Press"),
    "landmine_press": ("Landmine Shoulder Press", "Half-Kneeling Landmine Press"),
    "box_squat": ("Box Squats", "Barbell Box Squat"),
    "safety_bar_squat": ("SSB Squat", "Safety Squat Bar Squat", "Safety Bar Squats"),
    "pause_squat": ("Paused Squat", "Tempo Squat"),
    "sissy_squat": ("Sissy Squats",),
    "belt_squat": ("Belt Squats", "Belt Squat Machine"),
    "deficit_deadlift": ("Deficit DL", "Deficit Deadlifts"),
    "curtsy_lunge": ("Curtsy Lunges",),
    "cossack_squat": ("Cossack Squats",),
    "single_leg_hip_thrust": ("Single Leg Hip Thrust", "B-Stance Hip Thrust"),
    "lying_leg_curl": ("Lying Hamstring Curl", "Prone Leg Curl", "Lying Leg Curls"),
    "seated_leg_curl": ("Seated Hamstring Curl", "Seated Leg Curls"),
    "nordic_curl": ("Nordic Curl", "Nordic Ham Curl", "Nordics"),
    "glute_ham_raise": ("GHR", "Glute-Ham Raise"),
    "cable_pull_through": ("Pull-Through", "Cable Pull Through", "Rope Pull-Through"),
    "back_extension": ("Hyperextension", "Hyperextensions", "45 Degree Back Extension", "Back Extensions"),
    "kettlebell_swing": ("KB Swing", "Russian Kettlebell Swing", "Kettlebell Swings"),
    "cable_glute_kickback": ("Glute Kickback", "Cable Glute Kickbacks", "Donkey Kick"),
    "meadows_row": ("Landmine Row", "Meadows Rows"),
    "seal_row": ("Seal Rows", "Bench Seal Row"),
    "floor_press": ("Barbell Floor Press", "Dumbbell Floor Press", "DB Floor Press"),
    "db_pullover": ("DB Pullover", "Pullover", "Cross-Bench Pullover"),
    "reverse_curl": ("Reverse Barbell Curl", "Reverse Grip Curl", "Reverse Curls"),
    "cable_hammer_curl": ("Rope Hammer Curl", "Rope Curl"),
    "leg_press_calf_raise": ("Calf Press", "Leg Press Calf Press"),
    "donkey_calf_raise": ("Donkey Calf Raises",),
    "upright_row": ("Barbell Upright Row", "Cable Upright Row", "Dumbbell Upright Row", "Upright Rows"),
    "reverse_wrist_curl": ("Wrist Extension", "Reverse Wrist Curls", "Wrist Extensions"),
    "incline_cable_fly": ("Low-to-High Cable Fly", "Low Cable Fly", "Incline Cable Flyes"),
    "pistol_squat": ("Single-Leg Squat", "Pistol Squats"),
    "sit_up": ("Sit-up", "Situps", "Sit Ups"),
    "medicine_ball_slam": ("Med Ball Slam", "Ball Slam", "Medicine Ball Slams", "Med Ball Slams"),
    "wall_ball": ("Wall Balls", "Wall Ball Shot", "Medicine Ball Wall Throw"),
    "medicine_ball_chest_pass": ("Med Ball Chest Pass", "Medicine Ball Throw"),
    "medicine_ball_overhead_throw": ("Med Ball Overhead Throw", "Overhead Medicine Ball Throw"),
    "medicine_ball_sit_up": ("Med Ball Sit-up", "Medicine Ball Situp", "Med Ball Situp"),
    "barbell_rollout": ("BB Rollout", "Barbell Ab Rollout"),
    "stability_ball_rollout": ("Swiss Ball Rollout", "Stability Ball Ab Rollout"),
    "reverse_crunch": ("Reverse Crunches",),
    "flutter_kick": ("Flutter Kick",),
    "hollow_hold": ("Hollow Body Hold", "Hollow Body"),
    "bird_dog": ("Bird Dogs",),
    "toes_to_bar": ("Toes-to-Bar", "T2B"),
    "hanging_knee_raise": ("Hanging Knee Raises", "Knee Raise"),
    "box_jump": ("Box Jumps",),
    "sled_push": ("Prowler Push", "Sled Pushes"),
    "turkish_get_up": ("TGU", "Turkish Getup", "Turkish Get Up"),
    "wall_sit": ("Wall Sits", "Wall Squat Hold"),
}

ALIAS_NAME_TO_FAMILY: Dict[str, str] = {
    alias: slug for slug, aliases in _ALIASES.items() for alias in aliases
}

# ---------------------------------------------------------------------------
# Name resolution helpers (shared by the migration and the service)
# ---------------------------------------------------------------------------
_WS = re.compile(r"\s+")


def normalize_name(name: Optional[str]) -> str:
    """Case-fold and collapse whitespace so free-text names match the seed."""
    return _WS.sub(" ", (name or "").strip().lower())


_NAME_INDEX: Dict[str, str] = {}
# Canonical names win over aliases when both spell the same word.
for _alias, _slug in ALIAS_NAME_TO_FAMILY.items():
    _NAME_INDEX[normalize_name(_alias)] = _slug
for _canon, _slug in CANONICAL_NAME_TO_FAMILY.items():
    _NAME_INDEX[normalize_name(_canon)] = _slug


def family_for_name(name: Optional[str]) -> Optional[str]:
    """Resolve an exercise name (canonical, alias or free text) to a family slug.

    Exact case-insensitive match only — fuzzy matching is deliberately left to
    the caller so a custom "Bench Press Machine" never silently becomes the
    big-three bench.
    """
    if not name:
        return None
    return _NAME_INDEX.get(normalize_name(name))


def resolve_family_assignments(
    rows: Iterable[Tuple[str, str, Optional[str]]],
) -> Dict[str, Optional[str]]:
    """Compute ``exercise_id -> family slug`` for ``(id, name, canonical_id)`` rows.

    1. An exact name match (canonical or alias map) wins, so an alias that is
       split out of its group (``Dumbbell Shrugs``) gets its own family.
    2. Otherwise the row inherits the family of its ``canonical_id`` group —
       the group's canonical row if one resolved, else the group's majority.
    3. Otherwise ``None`` (cardio, sport, unknown custom names).
    """
    rows = list(rows)
    by_name: Dict[str, Optional[str]] = {}
    group_votes: Dict[str, Counter] = {}
    group_canonical: Dict[str, str] = {}

    for ex_id, name, canonical_id in rows:
        fam = family_for_name(name)
        by_name[ex_id] = fam
        if canonical_id and fam:
            group_votes.setdefault(canonical_id, Counter())[fam] += 1
            if normalize_name(name) in {
                normalize_name(c) for c in CANONICAL_NAME_TO_FAMILY
            }:
                group_canonical.setdefault(canonical_id, fam)

    result: Dict[str, Optional[str]] = {}
    for ex_id, _name, canonical_id in rows:
        fam = by_name[ex_id]
        if fam is None and canonical_id:
            fam = group_canonical.get(canonical_id)
            if fam is None and canonical_id in group_votes:
                fam = group_votes[canonical_id].most_common(1)[0][0]
        result[ex_id] = fam
    return result


__all__ = [
    "ALIAS_NAME_TO_FAMILY",
    "BIG_THREE_FAMILIES",
    "CANONICAL_NAME_TO_FAMILY",
    "FAMILY_DEFS",
    "family_for_name",
    "normalize_name",
    "resolve_family_assignments",
]
