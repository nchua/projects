#!/usr/bin/env python3
"""
Analyze exercise library for duplicates and inconsistencies.

This script connects to the database and produces a report of:
1. All exercises grouped by canonical_id
2. Orphaned exercises (null canonical_id)
3. Custom exercises that may duplicate seeded ones
4. Exercise usage counts (workout_exercises referencing each)
5. PR counts per exercise

Usage:
    cd backend
    source venv/bin/activate
    python scripts/analyze_exercises.py

Or with a specific database URL:
    DATABASE_URL=postgresql://... python scripts/analyze_exercises.py
"""

import os
import sys
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


def analyze_exercises(db_url: str):
    """Run exercise analysis and print report."""
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    db = Session()

    print("\n" + "=" * 70)
    print("EXERCISE LIBRARY ANALYSIS REPORT")
    print("=" * 70)

    # 1. Get all exercises
    print("\n--- 1. EXERCISE SUMMARY ---")
    result = db.execute(text("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN is_custom = true THEN 1 END) as custom,
            COUNT(CASE WHEN is_custom = false THEN 1 END) as seeded,
            COUNT(DISTINCT canonical_id) as unique_canonical
        FROM exercises
    """))
    row = result.fetchone()
    print(f"Total exercises: {row[0]}")
    print(f"  - Seeded: {row[2]}")
    print(f"  - Custom: {row[1]}")
    print(f"  - Unique canonical IDs: {row[3]}")

    # 2. Exercises grouped by canonical_id (find alias groups)
    print("\n--- 2. CANONICAL GROUPS (exercises sharing same canonical_id) ---")
    result = db.execute(text("""
        SELECT canonical_id, name, is_custom, category
        FROM exercises
        ORDER BY canonical_id, is_custom, name
    """))

    groups = defaultdict(list)
    for row in result:
        groups[row[0]].append({
            "name": row[1],
            "is_custom": row[2],
            "category": row[3]
        })

    # Show groups with multiple exercises (aliases)
    multi_groups = {k: v for k, v in groups.items() if len(v) > 1}
    print(f"\nFound {len(multi_groups)} alias groups with 2+ exercises:")
    for canonical_id, exercises in sorted(multi_groups.items(), key=lambda x: x[1][0]["name"]):
        names = [e["name"] for e in exercises]
        print(f"  - {names[0]}: {names}")

    # 3. Orphaned exercises (null canonical_id)
    print("\n--- 3. ORPHANED EXERCISES (null canonical_id) ---")
    result = db.execute(text("""
        SELECT id, name, category, is_custom
        FROM exercises
        WHERE canonical_id IS NULL
    """))
    orphans = result.fetchall()
    if orphans:
        print(f"Found {len(orphans)} exercises with NULL canonical_id:")
        for row in orphans:
            print(f"  - {row[1]} (id={row[0][:8]}..., custom={row[3]})")
    else:
        print("No orphaned exercises found.")

    # 4. Custom exercises that may duplicate seeded ones
    print("\n--- 4. POTENTIAL DUPLICATE CUSTOM EXERCISES ---")
    result = db.execute(text("""
        SELECT c.id, c.name, c.category, s.name as similar_seeded
        FROM exercises c
        JOIN exercises s ON LOWER(c.name) = LOWER(s.name) AND c.id != s.id
        WHERE c.is_custom = true AND s.is_custom = false
    """))
    duplicates = result.fetchall()
    if duplicates:
        print(f"Found {len(duplicates)} custom exercises matching seeded names:")
        for row in duplicates:
            print(f"  - Custom '{row[1]}' matches seeded '{row[3]}'")
    else:
        print("No duplicate custom exercises found.")

    # 5. Exercise usage counts
    print("\n--- 5. EXERCISE USAGE (top 20 most used) ---")
    result = db.execute(text("""
        SELECT e.name, e.is_custom, COUNT(we.id) as usage_count
        FROM exercises e
        LEFT JOIN workout_exercises we ON e.id = we.exercise_id
        GROUP BY e.id, e.name, e.is_custom
        ORDER BY usage_count DESC
        LIMIT 20
    """))
    usages = result.fetchall()
    if usages:
        for row in usages:
            custom_flag = " (custom)" if row[1] else ""
            if row[2] > 0:
                print(f"  {row[0]}{custom_flag}: {row[2]} workout(s)")
    else:
        print("No usage data found.")

    # 6. Exercises with PRs
    print("\n--- 6. EXERCISES WITH PRs (top 20) ---")
    result = db.execute(text("""
        SELECT e.name, e.is_custom, COUNT(p.id) as pr_count
        FROM exercises e
        LEFT JOIN prs p ON e.id = p.exercise_id
        GROUP BY e.id, e.name, e.is_custom
        HAVING COUNT(p.id) > 0
        ORDER BY pr_count DESC
        LIMIT 20
    """))
    prs = result.fetchall()
    if prs:
        for row in prs:
            custom_flag = " (custom)" if row[1] else ""
            print(f"  {row[0]}{custom_flag}: {row[2]} PR(s)")
    else:
        print("No PR data found.")

    # 7. Look for naming inconsistencies (similar names)
    print("\n--- 7. POTENTIAL NAMING INCONSISTENCIES ---")
    result = db.execute(text("""
        SELECT name FROM exercises WHERE is_custom = false ORDER BY name
    """))
    names = [row[0] for row in result.fetchall()]

    # Find names that differ only by 's' at the end (singular vs plural)
    singular_plural = []
    for name in names:
        if name.endswith('s'):
            singular = name[:-1]
            if singular in names:
                singular_plural.append((singular, name))

    if singular_plural:
        print("Singular/plural pairs found (should be aliases, not separate):")
        for s, p in singular_plural:
            print(f"  - '{s}' vs '{p}'")
    else:
        print("No singular/plural inconsistencies found.")

    # 8. List all one-arm exercises
    print("\n--- 8. ONE-ARM EXERCISES ---")
    result = db.execute(text("""
        SELECT name, category FROM exercises
        WHERE LOWER(name) LIKE '%one-arm%'
           OR LOWER(name) LIKE '%one arm%'
           OR LOWER(name) LIKE '%single arm%'
           OR LOWER(name) LIKE '%1-arm%'
        ORDER BY name
    """))
    one_arm = result.fetchall()
    if one_arm:
        print(f"Found {len(one_arm)} one-arm exercises:")
        for row in one_arm:
            print(f"  - {row[0]} ({row[1]})")
    else:
        print("No one-arm exercises found. Run migration to add them.")

    print("\n" + "=" * 70)
    print("REPORT COMPLETE")
    print("=" * 70 + "\n")

    db.close()


if __name__ == "__main__":
    db_url = get_database_url()
    print(f"Connecting to: {db_url[:50]}...")
    analyze_exercises(db_url)
