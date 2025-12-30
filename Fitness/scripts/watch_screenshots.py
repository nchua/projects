#!/usr/bin/env python3
"""
Workout Screenshot Watcher

Watches the screenshot folder for new images and automatically processes them.
Runs as a background service.

Usage:
    python watch_screenshots.py
    python watch_screenshots.py --daemon  # Run as background process
"""

import os
import sys
import time
import shutil
import logging
from pathlib import Path
from datetime import datetime

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileCreatedEvent
except ImportError:
    print("Error: watchdog package not installed. Run: pip install watchdog")
    sys.exit(1)

# Import processing function
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
from process_workout_screenshot import process_screenshot, SCREENSHOT_DIR, PROCESSED_DIR, WORKOUT_LOG_PATH

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Dashboard sync
DASHBOARD_DIR = SCRIPT_DIR.parent / "dashboard"


class WorkoutScreenshotHandler(FileSystemEventHandler):
    """Handler for new workout screenshot files."""

    def __init__(self):
        self.processed_files = set()
        self.cooldown = {}  # Prevent duplicate processing

    def on_created(self, event):
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        # Only process image files
        if file_path.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.gif', '.webp'}:
            return

        # Skip files in processed folder
        if 'processed' in str(file_path):
            return

        # Cooldown to prevent duplicate events
        now = time.time()
        if file_path.name in self.cooldown:
            if now - self.cooldown[file_path.name] < 5:
                return
        self.cooldown[file_path.name] = now

        # Wait a moment for file to finish writing
        time.sleep(1)

        logger.info(f"New screenshot detected: {file_path.name}")
        self.process_new_screenshot(file_path)

    def process_new_screenshot(self, file_path: Path):
        """Process a new screenshot and sync to dashboard."""
        try:
            # Process the screenshot
            success = process_screenshot(str(file_path), move_to_processed=True)

            if success:
                logger.info(f"Successfully processed: {file_path.name}")

                # Sync workout log to dashboard folder
                self.sync_to_dashboard()
            else:
                logger.error(f"Failed to process: {file_path.name}")

        except Exception as e:
            logger.error(f"Error processing {file_path.name}: {e}")

    def sync_to_dashboard(self):
        """Copy workout_log.json to dashboard folder."""
        if WORKOUT_LOG_PATH.exists() and DASHBOARD_DIR.exists():
            dest = DASHBOARD_DIR / "workout_log.json"
            shutil.copy(str(WORKOUT_LOG_PATH), str(dest))
            logger.info("Synced workout_log.json to dashboard")


def check_environment():
    """Check if required environment variables are set."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        logger.error("ANTHROPIC_API_KEY environment variable not set!")
        logger.error("Set it with: export ANTHROPIC_API_KEY='your-api-key'")
        return False
    return True


def run_watcher():
    """Run the screenshot watcher."""
    if not check_environment():
        sys.exit(1)

    # Ensure directories exist
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 50)
    logger.info("Workout Screenshot Watcher Started")
    logger.info(f"Watching: {SCREENSHOT_DIR}")
    logger.info(f"Processed folder: {PROCESSED_DIR}")
    logger.info("=" * 50)
    logger.info("Drop workout screenshots into the watched folder")
    logger.info("Press Ctrl+C to stop\n")

    event_handler = WorkoutScreenshotHandler()
    observer = Observer()
    observer.schedule(event_handler, str(SCREENSHOT_DIR), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("\nStopping watcher...")
        observer.stop()

    observer.join()
    logger.info("Watcher stopped")


def run_daemon():
    """Run as a background daemon process."""
    import subprocess

    # Get the path to this script
    script_path = Path(__file__).resolve()

    # Create a simple shell wrapper that runs in background
    cmd = f'nohup python3 "{script_path}" > /tmp/workout_watcher.log 2>&1 &'

    subprocess.run(cmd, shell=True)
    logger.info("Watcher started as background process")
    logger.info("Logs: /tmp/workout_watcher.log")
    logger.info("To stop: pkill -f watch_screenshots.py")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--daemon":
        run_daemon()
    else:
        run_watcher()


if __name__ == "__main__":
    main()
