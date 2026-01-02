#!/usr/bin/env python3
"""Seed real workout data from workout_log.json for a user."""

import requests
import json
from datetime import datetime

BASE_URL = "https://backend-production-e316.up.railway.app"
EMAIL = "test@example.com"
PASSWORD = "TestPass123"

# Load real workout data
WORKOUT_LOG_PATH = "/Users/nickchua/Desktop/AI/Fitness/workout_log.json"

with open(WORKOUT_LOG_PATH, "r") as f:
    workout_data = json.load(f)

# Extract user context for bodyweight exercises
user_context = workout_data.get("user_context", {})
USER_BODYWEIGHT = user_context.get("bodyweight_lb", 166)

# Login
resp = requests.post(f"{BASE_URL}/auth/login", json={"email": EMAIL, "password": PASSWORD})
token = resp.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Get exercises to map names to IDs
exercises = requests.get(f"{BASE_URL}/exercises", headers=headers).json()

def find_exercise(name):
    """Find exercise ID by name (fuzzy match)"""
    name_lower = name.lower()

    # First try exact match
    for e in exercises:
        if e["name"].lower() == name_lower:
            return e["id"]

    # Then try contains match
    for e in exercises:
        if name_lower in e["name"].lower() or e["name"].lower() in name_lower:
            return e["id"]

    # Special mappings
    mappings = {
        "back squat": ["squat", "bb squat", "barbell squat"],
        "bench press": ["flat bench", "bb bench"],
        "overhead press": ["ohp", "shoulder press", "military press"],
        "romanian deadlift": ["rdl", "stiff leg"],
        "bent over row": ["barbell row", "bb row"],
        "lateral shoulder raise": ["lateral raise", "side raise"],
        "triceps pulldown": ["tricep pushdown", "rope pushdown"],
        "incline bench press": ["incline bench", "incline press"],
        "barbell curl": ["bb curl", "bicep curl"],
        "alternating lunge": ["walking lunge", "lunge"],
        "dumbbell high pull": ["high pull", "upright row"],
        "chest dip": ["dip", "parallel bar dip"],
        "pull-up": ["pullup", "chin up", "chinup"],
        "calf raise": ["calf press", "seated calf"],
    }

    for key, alternatives in mappings.items():
        if name_lower in key or key in name_lower:
            for alt in alternatives:
                for e in exercises:
                    if alt in e["name"].lower():
                        return e["id"]
        for alt in alternatives:
            if alt in name_lower:
                for e in exercises:
                    if key in e["name"].lower():
                        return e["id"]

    return None

# First, delete all existing workouts for this user
print("Clearing existing workouts...")
existing = requests.get(f"{BASE_URL}/workouts?limit=100", headers=headers).json()
for workout in existing:
    resp = requests.delete(f"{BASE_URL}/workouts/{workout['id']}", headers=headers)
    if resp.status_code in [200, 204]:
        print(f"  Deleted: {workout['date']}")

# Clear bodyweight entries
print("\nClearing existing bodyweight entries...")
bw_history = requests.get(f"{BASE_URL}/bodyweight?limit=100", headers=headers).json()
for entry in bw_history.get("entries", []):
    resp = requests.delete(f"{BASE_URL}/bodyweight/{entry['id']}", headers=headers)
    if resp.status_code in [200, 204]:
        print(f"  Deleted: {entry['date']}")

print("\n" + "="*50)
print("Creating workouts from your real data...")
print("="*50)

workouts_created = 0
exercises_not_found = set()

for session in workout_data["workout_sessions"]:
    exercises_data = []

    for ex_idx, ex in enumerate(session["exercises"]):
        exercise_id = find_exercise(ex["name"])

        if not exercise_id:
            exercises_not_found.add(ex["name"])
            continue

        sets_data = []
        set_number = 1

        for set_info in ex["sets"]:
            # Skip warmup sets
            if set_info.get("is_warmup"):
                continue

            # Handle "sets" field (multiple identical sets)
            num_sets = set_info.get("sets", 1)
            weight = set_info.get("weight_lb", 0)
            reps = set_info.get("reps", 0)

            # For bodyweight exercises, use user's bodyweight
            if weight == 0 and ex.get("equipment") == "bodyweight":
                weight = USER_BODYWEIGHT

            for _ in range(num_sets):
                sets_data.append({
                    "weight": weight,
                    "weight_unit": "lb",
                    "reps": reps,
                    "set_number": set_number
                })
                set_number += 1

        if sets_data:
            exercises_data.append({
                "exercise_id": exercise_id,
                "order_index": ex_idx,
                "sets": sets_data
            })

    if not exercises_data:
        print(f"Skipped: {session['date']} - no valid exercises")
        continue

    # Convert date to datetime format (API expects ISO datetime)
    date_str = session["date"]
    if len(date_str) == 10:  # Just a date like "2025-12-30"
        date_str = f"{date_str}T12:00:00"

    workout_payload = {
        "date": date_str,
        "duration_minutes": session.get("duration_minutes"),
        "notes": session.get("session_name", ""),
        "exercises": exercises_data
    }

    resp = requests.post(f"{BASE_URL}/workouts", headers=headers, json=workout_payload)
    if resp.status_code in [200, 201]:
        workouts_created += 1
        session_name = session.get("session_name", "Workout")
        print(f"✓ Created: {session['date']} - {session_name}")
    else:
        print(f"✗ Failed: {session['date']} - {resp.status_code} - {resp.text[:100]}")

# Add real bodyweight entry
print("\n" + "="*50)
print("Adding bodyweight entry...")
print("="*50)

user_context = workout_data.get("user_context", {})
bodyweight = user_context.get("bodyweight_lb", 166)

resp = requests.post(
    f"{BASE_URL}/bodyweight",
    headers=headers,
    json={"weight": bodyweight, "date": "2025-12-29", "weight_unit": "lb"}
)
if resp.status_code in [200, 201]:
    print(f"✓ Added bodyweight: {bodyweight} lb")

# Update profile with real data
print("\n" + "="*50)
print("Updating profile with your data...")
print("="*50)

profile_update = {
    "age": user_context.get("age_years", 29),
    "sex": "M",  # male -> M
    "bodyweight_lb": bodyweight,
}

resp = requests.put(f"{BASE_URL}/profile", headers=headers, json=profile_update)
if resp.status_code == 200:
    print(f"✓ Profile updated: Age {profile_update['age']}, {bodyweight} lb")
else:
    print(f"✗ Profile update failed: {resp.text[:100]}")

print("\n" + "="*50)
print(f"Summary:")
print(f"  Workouts created: {workouts_created}")
print(f"  Your bodyweight: {bodyweight} lb")
print("="*50)

if exercises_not_found:
    print(f"\n⚠ Exercises not found in database (skipped):")
    for name in sorted(exercises_not_found):
        print(f"  - {name}")

print(f"\nLogin with:")
print(f"  Email: {EMAIL}")
print(f"  Password: {PASSWORD}")
