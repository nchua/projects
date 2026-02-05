#!/usr/bin/env python3
"""
Backfill goal progress snapshots from existing PR history.

This script creates initial GoalProgressSnapshot records for existing goals
by looking up PR history for each goal's exercise.

Usage:
    cd backend
    source venv/bin/activate
    python scripts/backfill_goal_progress.py

Or with a specific database URL:
    DATABASE_URL=postgresql://... python scripts/backfill_goal_progress.py

Options:
    --dry-run    Show what would be created without actually creating records
"""

import os
import sys
import argparse
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import uuid

from app.models.mission import Goal, GoalProgressSnapshot, GoalStatus
from app.models.pr import PR


def get_database_url():
    """Get database URL from environment or use default."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("Warning: DATABASE_URL not set, using local SQLite")
        url = "sqlite:///./fitness.db"
    return url


def backfill_goal_progress(db_url: str, dry_run: bool = False):
    """Create progress snapshots from PR history for existing goals."""
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    db = Session()

    print("\n" + "=" * 70)
    print("GOAL PROGRESS BACKFILL")
    print("=" * 70)

    if dry_run:
        print("\n*** DRY RUN - No records will be created ***\n")

    # Get all active goals
    goals = db.query(Goal).filter(Goal.status == GoalStatus.ACTIVE.value).all()
    print(f"\nFound {len(goals)} active goals to process")

    total_snapshots_created = 0
    goals_processed = 0

    for goal in goals:
        print(f"\n--- Goal: {goal.id[:8]}... ---")
        print(f"  Exercise ID: {goal.exercise_id}")
        print(f"  Created: {goal.created_at}")
        print(f"  Starting e1RM: {goal.starting_e1rm}")
        print(f"  Current e1RM: {goal.current_e1rm}")

        # Check for existing snapshots
        existing_snapshots = db.query(GoalProgressSnapshot).filter(
            GoalProgressSnapshot.goal_id == goal.id
        ).count()

        if existing_snapshots > 0:
            print(f"  Skipping: already has {existing_snapshots} snapshots")
            continue

        # Get PRs for this exercise since goal creation
        prs = db.query(PR).filter(
            PR.user_id == goal.user_id,
            PR.exercise_id == goal.exercise_id,
            PR.achieved_at >= goal.created_at
        ).order_by(PR.achieved_at).all()

        print(f"  Found {len(prs)} PRs since goal creation")

        snapshots_to_create = []

        # Add starting point snapshot if we have starting_e1rm
        if goal.starting_e1rm:
            snapshots_to_create.append({
                "goal_id": goal.id,
                "recorded_at": goal.created_at,
                "e1rm": goal.starting_e1rm,
                "weight": None,
                "reps": None,
                "workout_id": None
            })

        # Add snapshots for each PR
        for pr in prs:
            # Use e1RM value from PR
            e1rm = pr.value if pr.value else None
            if e1rm:
                snapshots_to_create.append({
                    "goal_id": goal.id,
                    "recorded_at": pr.achieved_at,
                    "e1rm": e1rm,
                    "weight": pr.weight,
                    "reps": pr.reps,
                    "workout_id": None  # We don't have workout_id in PR model
                })

        # Remove duplicates (same date, keep higher e1rm)
        seen_dates = {}
        for snapshot in snapshots_to_create:
            date_key = snapshot["recorded_at"].date() if snapshot["recorded_at"] else None
            if date_key:
                if date_key not in seen_dates or snapshot["e1rm"] > seen_dates[date_key]["e1rm"]:
                    seen_dates[date_key] = snapshot

        unique_snapshots = list(seen_dates.values())
        print(f"  Will create {len(unique_snapshots)} snapshots (after dedup)")

        if not dry_run:
            for snapshot_data in unique_snapshots:
                snapshot = GoalProgressSnapshot(
                    id=str(uuid.uuid4()),
                    goal_id=snapshot_data["goal_id"],
                    recorded_at=snapshot_data["recorded_at"],
                    e1rm=snapshot_data["e1rm"],
                    weight=snapshot_data["weight"],
                    reps=snapshot_data["reps"],
                    workout_id=snapshot_data["workout_id"]
                )
                db.add(snapshot)

            total_snapshots_created += len(unique_snapshots)

        goals_processed += 1

    if not dry_run:
        db.commit()
        print(f"\n{'=' * 70}")
        print(f"BACKFILL COMPLETE")
        print(f"  Goals processed: {goals_processed}")
        print(f"  Snapshots created: {total_snapshots_created}")
        print(f"{'=' * 70}\n")
    else:
        print(f"\n{'=' * 70}")
        print(f"DRY RUN COMPLETE")
        print(f"  Goals that would be processed: {goals_processed}")
        print(f"  Snapshots that would be created: {len([s for g in goals for s in []])}+")
        print(f"{'=' * 70}\n")

    db.close()


def main():
    parser = argparse.ArgumentParser(description="Backfill goal progress snapshots from PR history")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be created without creating")
    args = parser.parse_args()

    db_url = get_database_url()
    print(f"Using database: {db_url[:50]}...")

    backfill_goal_progress(db_url, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
