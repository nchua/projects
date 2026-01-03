#!/usr/bin/env python3
"""Import workout data from workout_log.json into the fitness app backend."""

import json
import requests

BASE_URL = "http://localhost:8000"
TOKEN = None

def login():
    """Login and get token."""
    global TOKEN
    # Try to login first
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "test@example.com",
        "password": "TestPass123!"
    })
    if resp.status_code == 200:
        TOKEN = resp.json()["access_token"]
        print("Logged in successfully")
        return True

    # If login fails, register
    resp = requests.post(f"{BASE_URL}/auth/register", json={
        "email": "test@example.com",
        "password": "TestPass123!"
    })
    if resp.status_code == 200:
        print("Registered new user")

    # Now login
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "test@example.com",
        "password": "TestPass123!"
    })
    if resp.status_code == 200:
        TOKEN = resp.json()["access_token"]
        print("Logged in successfully")
        return True

    print(f"Login failed: {resp.json()}")
    return False

def headers():
    return {"Authorization": f"Bearer {TOKEN}"}

def update_profile(user_context):
    """Update user profile with context data."""
    profile = {
        "age": user_context.get("age_years"),
        "sex": user_context.get("sex"),
        "bodyweight": user_context.get("bodyweight_lb"),
        "height_inches": user_context.get("height_in"),
        "training_experience": "intermediate",
        "preferred_unit": "lb",
        "e1rm_formula": "epley"
    }
    resp = requests.put(f"{BASE_URL}/profile", json=profile, headers=headers())
    if resp.status_code == 200:
        print(f"Profile updated: {user_context.get('age_years')}yo, {user_context.get('bodyweight_lb')}lb")
    else:
        print(f"Profile update failed: {resp.text}")

def get_exercise_id(name):
    """Get exercise ID by name."""
    resp = requests.get(f"{BASE_URL}/exercises?search={name}", headers=headers())
    if resp.status_code == 200:
        exercises = resp.json()
        if exercises:
            return exercises[0]["id"]
    return None

def import_workout(session):
    """Import a single workout session."""
    date = session["date"]
    notes = session.get("session_name", "")

    exercises = []
    for idx, ex in enumerate(session.get("exercises", [])):
        exercise_name = ex["name"]
        exercise_id = get_exercise_id(exercise_name)

        if not exercise_id:
            print(f"  Warning: Exercise '{exercise_name}' not found, skipping")
            continue

        sets = []
        set_number = 1
        for s in ex.get("sets", []):
            # Skip warmup sets
            if s.get("is_warmup"):
                continue

            weight = s.get("weight_lb", 0)
            reps = s.get("reps", 0)
            num_sets = s.get("sets", 1)

            # Expand multiple sets
            for _ in range(num_sets):
                sets.append({
                    "weight": weight,
                    "weight_unit": "lb",
                    "reps": reps,
                    "rpe": None,
                    "rir": None,
                    "set_number": set_number
                })
                set_number += 1

        if sets:
            exercises.append({
                "exercise_id": exercise_id,
                "order_index": idx,
                "sets": sets
            })

    if not exercises:
        print(f"  No valid exercises for {date}, skipping")
        return False

    workout = {
        "date": date,
        "duration_minutes": session.get("duration_minutes"),
        "session_rpe": None,
        "notes": notes,
        "exercises": exercises
    }

    resp = requests.post(f"{BASE_URL}/workouts", json=workout, headers=headers())
    if resp.status_code == 200:
        result = resp.json()
        print(f"  Imported: {date} - {notes} ({len(exercises)} exercises)")
        return True
    else:
        print(f"  Failed to import {date}: {resp.text}")
        return False

def main():
    # Load workout data
    with open("/Users/nickchua/Desktop/AI/Fitness/workout_log.json") as f:
        data = json.load(f)

    print("=" * 50)
    print("Fitness App Data Import")
    print("=" * 50)

    # Login/register
    if not login():
        return

    # Update profile
    if "user_context" in data:
        update_profile(data["user_context"])

    # Import workouts
    sessions = data.get("workout_sessions", [])
    print(f"\nImporting {len(sessions)} workout sessions...")

    imported = 0
    for session in sessions:
        if import_workout(session):
            imported += 1

    print(f"\nImported {imported}/{len(sessions)} workouts")

    # Test analytics
    print("\n" + "=" * 50)
    print("Testing Analytics")
    print("=" * 50)

    # Get PRs
    resp = requests.get(f"{BASE_URL}/analytics/prs", headers=headers())
    if resp.status_code == 200:
        prs = resp.json()
        print(f"\nPRs detected: {prs['total_count']}")
        for pr in prs["prs"][:5]:
            if pr["pr_type"] == "e1rm":
                print(f"  {pr['exercise_name']}: {pr['value']:.1f}lb e1RM")
            else:
                print(f"  {pr['exercise_name']}: {pr['reps']} reps @ {pr['weight']:.1f}lb")

    # Get weekly review
    resp = requests.get(f"{BASE_URL}/analytics/weekly-review", headers=headers())
    if resp.status_code == 200:
        review = resp.json()
        print(f"\nWeekly Review:")
        print(f"  Total workouts: {review['total_workouts']}")
        print(f"  Total sets: {review['total_sets']}")
        print(f"  Total volume: {review['total_volume']:.0f}lb")

    print("\nDone!")

if __name__ == "__main__":
    main()
