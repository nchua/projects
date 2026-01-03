#!/usr/bin/env python3
"""
Watch workout_log.json for changes and auto-sync to the fitness app.

Usage:
    python watch_workout_log.py

This script monitors the workout log file and automatically imports
new workouts when the file changes.
"""

import subprocess
import sys
import time
import hashlib
from pathlib import Path

WORKOUT_LOG_PATH = Path("/Users/nickchua/Desktop/AI/Fitness/workout_log.json")
SEED_SCRIPT = Path(__file__).parent / "seed_user_data.py"
CHECK_INTERVAL = 5  # seconds


def get_file_hash(filepath: Path) -> str:
    """Get MD5 hash of file contents."""
    if not filepath.exists():
        return ""
    return hashlib.md5(filepath.read_bytes()).hexdigest()


def sync_workouts():
    """Run the seed script to sync workouts."""
    print(f"\n{'='*50}")
    print(f"Change detected! Syncing workouts...")
    print(f"{'='*50}\n")

    result = subprocess.run(
        [sys.executable, str(SEED_SCRIPT)],
        cwd=SEED_SCRIPT.parent,
        capture_output=False
    )

    if result.returncode == 0:
        print(f"\n{'='*50}")
        print("Sync complete! Refresh the app to see changes.")
        print(f"{'='*50}\n")
    else:
        print(f"\nSync failed with code {result.returncode}")


def main():
    print(f"Watching: {WORKOUT_LOG_PATH}")
    print(f"Check interval: {CHECK_INTERVAL}s")
    print("Press Ctrl+C to stop\n")

    last_hash = get_file_hash(WORKOUT_LOG_PATH)
    print(f"Initial hash: {last_hash[:8]}...")

    try:
        while True:
            time.sleep(CHECK_INTERVAL)
            current_hash = get_file_hash(WORKOUT_LOG_PATH)

            if current_hash != last_hash:
                print(f"Hash changed: {last_hash[:8]}... -> {current_hash[:8]}...")
                sync_workouts()
                last_hash = current_hash
    except KeyboardInterrupt:
        print("\nStopped watching.")


if __name__ == "__main__":
    main()
