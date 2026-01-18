#!/usr/bin/env python3
"""
Clean up duplicate exercises in the database.

This script:
1. Finds exercises that are semantically the same but have different canonical_ids
   (e.g., standalone "Calf Raise" vs "Calf Raise" as alias of "Standing Calf Raise")
2. Shows a preview of what would be merged
3. Optionally executes the merge (updates workout_exercises and prs, deletes duplicates)

Usage:
    cd backend
    source venv/bin/activate

    # Preview mode (default - shows what would be merged)
    DATABASE_URL=$DATABASE_URL python scripts/cleanup_exercises.py

    # Execute mode (actually performs the merge)
    DATABASE_URL=$DATABASE_URL python scripts/cleanup_exercises.py --execute

    # Verbose mode (show all exercises, not just duplicates)
    DATABASE_URL=$DATABASE_URL python scripts/cleanup_exercises.py --verbose
"""

import os
import sys
import argparse
from collections import defaultdict

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


def get_database_url():
    """Get database URL from environment or use default."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("Warning: DATABASE_URL not set, using local SQLite")
        url = "sqlite:///./fitness.db"
    return url


def find_duplicates(db):
    """
    Find exercises that appear to be duplicates based on name similarity.

    Returns a list of tuples: (duplicate_exercise, canonical_exercise)
    where duplicate should be merged into canonical.
    """
    duplicates = []

    # Find exercises with the same name (case-insensitive) but different canonical_ids
    result = db.execute(text("""
        SELECT
            e1.id as dup_id,
            e1.name as dup_name,
            e1.canonical_id as dup_canonical,
            e1.is_custom as dup_is_custom,
            e2.id as canon_id,
            e2.name as canon_name,
            e2.canonical_id as canon_canonical,
            e2.is_custom as canon_is_custom
        FROM exercises e1
        JOIN exercises e2 ON LOWER(e1.name) = LOWER(e2.name)
        WHERE e1.id != e2.id
          AND e1.canonical_id != e2.canonical_id
          AND e1.is_custom = false
          AND e2.is_custom = false
        ORDER BY e1.name
    """))

    seen_pairs = set()
    for row in result:
        # Create a normalized pair key to avoid duplicates
        pair_key = tuple(sorted([row[0], row[4]]))
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)

        # Determine which is the "canonical" one (prefer the one that IS the canonical)
        # If e2's id == e2's canonical_id, then e2 is the primary and e1 is the duplicate
        if row[4] == row[6]:  # canon_id == canon_canonical
            duplicates.append({
                "duplicate": {
                    "id": row[0],
                    "name": row[1],
                    "canonical_id": row[2],
                    "is_custom": row[3]
                },
                "canonical": {
                    "id": row[4],
                    "name": row[5],
                    "canonical_id": row[6],
                    "is_custom": row[7]
                }
            })
        elif row[0] == row[2]:  # dup_id == dup_canonical
            duplicates.append({
                "duplicate": {
                    "id": row[4],
                    "name": row[5],
                    "canonical_id": row[6],
                    "is_custom": row[7]
                },
                "canonical": {
                    "id": row[0],
                    "name": row[1],
                    "canonical_id": row[2],
                    "is_custom": row[3]
                }
            })
        else:
            # Neither is the primary canonical - pick one arbitrarily (by name length, shorter is more canonical)
            if len(row[1]) <= len(row[5]):
                duplicates.append({
                    "duplicate": {
                        "id": row[4],
                        "name": row[5],
                        "canonical_id": row[6],
                        "is_custom": row[7]
                    },
                    "canonical": {
                        "id": row[0],
                        "name": row[1],
                        "canonical_id": row[2],
                        "is_custom": row[3]
                    }
                })
            else:
                duplicates.append({
                    "duplicate": {
                        "id": row[0],
                        "name": row[1],
                        "canonical_id": row[2],
                        "is_custom": row[3]
                    },
                    "canonical": {
                        "id": row[4],
                        "name": row[5],
                        "canonical_id": row[6],
                        "is_custom": row[7]
                    }
                })

    return duplicates


def get_usage_counts(db, exercise_id):
    """Get workout and PR counts for an exercise."""
    workout_result = db.execute(text(
        "SELECT COUNT(*) FROM workout_exercises WHERE exercise_id = :id"
    ), {"id": exercise_id})
    workout_count = workout_result.scalar()

    pr_result = db.execute(text(
        "SELECT COUNT(*) FROM prs WHERE exercise_id = :id"
    ), {"id": exercise_id})
    pr_count = pr_result.scalar()

    return {"workouts": workout_count, "prs": pr_count}


def preview_duplicates(db, duplicates):
    """Show what would be merged."""
    print("\n" + "=" * 70)
    print("DUPLICATE EXERCISE PREVIEW")
    print("=" * 70)

    if not duplicates:
        print("\nNo duplicate exercises found!")
        return

    print(f"\nFound {len(duplicates)} duplicate(s) to merge:\n")

    for i, dup_info in enumerate(duplicates, 1):
        dup = dup_info["duplicate"]
        canon = dup_info["canonical"]

        dup_usage = get_usage_counts(db, dup["id"])
        canon_usage = get_usage_counts(db, canon["id"])

        print(f"{i}. MERGE: '{dup['name']}' → '{canon['name']}'")
        print(f"   Duplicate ID: {dup['id'][:8]}... (workouts: {dup_usage['workouts']}, PRs: {dup_usage['prs']})")
        print(f"   Canonical ID: {canon['id'][:8]}... (workouts: {canon_usage['workouts']}, PRs: {canon_usage['prs']})")
        print()

    print("-" * 70)
    print("To execute these merges, run with --execute flag")
    print("-" * 70)


def execute_merge(db, duplicates, dry_run=False):
    """Execute the merge operations."""
    print("\n" + "=" * 70)
    print("EXECUTING DUPLICATE CLEANUP" + (" (DRY RUN)" if dry_run else ""))
    print("=" * 70)

    if not duplicates:
        print("\nNo duplicates to merge.")
        return

    for i, dup_info in enumerate(duplicates, 1):
        dup = dup_info["duplicate"]
        canon = dup_info["canonical"]

        dup_usage = get_usage_counts(db, dup["id"])

        print(f"\n{i}. Merging '{dup['name']}' → '{canon['name']}'")

        # Update workout_exercises
        if dup_usage["workouts"] > 0:
            print(f"   - Updating {dup_usage['workouts']} workout_exercises...")
            if not dry_run:
                db.execute(text("""
                    UPDATE workout_exercises
                    SET exercise_id = :canon_id
                    WHERE exercise_id = :dup_id
                """), {"canon_id": canon["id"], "dup_id": dup["id"]})

        # Update PRs
        if dup_usage["prs"] > 0:
            print(f"   - Updating {dup_usage['prs']} PRs...")
            if not dry_run:
                db.execute(text("""
                    UPDATE prs
                    SET exercise_id = :canon_id
                    WHERE exercise_id = :dup_id
                """), {"canon_id": canon["id"], "dup_id": dup["id"]})

        # Delete duplicate exercise
        print(f"   - Deleting duplicate exercise entry...")
        if not dry_run:
            db.execute(text("""
                DELETE FROM exercises WHERE id = :dup_id
            """), {"dup_id": dup["id"]})

    if not dry_run:
        db.commit()
        print("\n" + "=" * 70)
        print(f"CLEANUP COMPLETE - {len(duplicates)} duplicate(s) merged")
        print("=" * 70)
    else:
        print("\n(Dry run - no changes made)")


def main():
    parser = argparse.ArgumentParser(description="Clean up duplicate exercises")
    parser.add_argument("--execute", action="store_true",
                        help="Execute the merge (default is preview only)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show verbose output")
    args = parser.parse_args()

    db_url = get_database_url()
    print(f"Connecting to: {db_url[:50]}...")

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        duplicates = find_duplicates(db)

        if args.execute:
            execute_merge(db, duplicates)
        else:
            preview_duplicates(db, duplicates)

    except Exception as e:
        print(f"\nError: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
