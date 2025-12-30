#!/usr/bin/env python3
"""
Workout Screenshot Processor

Processes workout screenshots from fitness apps and extracts structured data
to add to workout_log.json. Can be run manually or via the watcher script.

Usage:
    python process_workout_screenshot.py <image_path>
    python process_workout_screenshot.py --folder <folder_path>
"""

import os
import sys
import json
import base64
import shutil
from datetime import datetime
from pathlib import Path

try:
    import anthropic
except ImportError:
    print("Error: anthropic package not installed. Run: pip install anthropic")
    sys.exit(1)

# Paths
SCRIPT_DIR = Path(__file__).parent
FITNESS_DIR = SCRIPT_DIR.parent
WORKOUT_LOG_PATH = FITNESS_DIR / "workout_log.json"
SCREENSHOT_DIR = FITNESS_DIR / "Workout Log Screenshot"
PROCESSED_DIR = SCREENSHOT_DIR / "processed"

# Ensure processed directory exists
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

EXTRACTION_PROMPT = """Analyze this workout screenshot from a fitness tracking app.

Extract ALL workout data visible in the image and return it as JSON in this exact format:

{
  "session_date": "YYYY-MM-DD or null if not visible",
  "session_name": "Name of workout if shown (e.g., 'Upper Three', 'Leg Day')",
  "duration_minutes": number or null,
  "summary": {
    "tonnage_lb": total weight lifted in pounds,
    "total_reps": total reps across all exercises
  },
  "exercises": [
    {
      "name": "Exercise Name",
      "equipment": "barbell|dumbbell|cable|bodyweight|machine",
      "variation": "any variation noted (e.g., 'seated', 'incline')",
      "sets": [
        {
          "weight_lb": weight in pounds (0 for bodyweight),
          "reps": number of reps,
          "sets": number of sets at this weight/rep combo,
          "is_warmup": true if this appears to be a warmup set (lighter weight, higher reps before working sets)
        }
      ],
      "total_reps": total reps for this exercise,
      "total_volume_lb": total volume (weight x reps) for this exercise
    }
  ]
}

Important:
- Convert all weights to pounds (lb)
- Mark warmup sets based on the progression pattern (lighter weights before working sets)
- If the same weight/rep combo is done multiple times, consolidate into one entry with sets > 1
- For bodyweight exercises, use weight_lb: 0
- For dumbbell exercises, note if the weight shown is per dumbbell or total
- Extract the exact numbers shown - don't estimate
- If you can see a date or time, extract it
- Return ONLY valid JSON, no other text"""


def encode_image(image_path: str) -> tuple[str, str]:
    """Encode image to base64 and determine media type."""
    ext = Path(image_path).suffix.lower()
    media_types = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.webp': 'image/webp'
    }
    media_type = media_types.get(ext, 'image/png')

    with open(image_path, 'rb') as f:
        data = base64.standard_b64encode(f.read()).decode('utf-8')

    return data, media_type


def extract_workout_data(image_path: str, client: anthropic.Anthropic) -> dict:
    """Use Claude to extract workout data from screenshot."""
    print(f"  Analyzing image with Claude...")

    image_data, media_type = encode_image(image_path)

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data
                        }
                    },
                    {
                        "type": "text",
                        "text": EXTRACTION_PROMPT
                    }
                ]
            }
        ]
    )

    response_text = message.content[0].text.strip()

    # Clean up response - remove markdown code blocks if present
    if response_text.startswith('```'):
        lines = response_text.split('\n')
        # Remove first and last lines (```json and ```)
        response_text = '\n'.join(lines[1:-1])

    try:
        return json.loads(response_text)
    except json.JSONDecodeError as e:
        print(f"  Warning: Failed to parse JSON response: {e}")
        print(f"  Response was: {response_text[:500]}...")
        return None


def load_workout_log() -> dict:
    """Load existing workout log or create new one."""
    if WORKOUT_LOG_PATH.exists():
        with open(WORKOUT_LOG_PATH, 'r') as f:
            return json.load(f)

    return {
        "schema_version": "1.0",
        "units": {"weight": "lb"},
        "user_context": {
            "sex": "male",
            "age_years": 29,
            "height_in": 69,
            "bodyweight_lb": 166
        },
        "workout_sessions": [],
        "performance_notes": []
    }


def save_workout_log(data: dict):
    """Save workout log to file."""
    with open(WORKOUT_LOG_PATH, 'w') as f:
        json.dump(data, f, indent=2)


def generate_session_id(date: str, session_name: str = None) -> str:
    """Generate a unique session ID."""
    date_part = date or datetime.now().strftime("%Y-%m-%d")
    name_part = session_name.lower().replace(" ", "_") if session_name else "workout"
    return f"sess_{date_part}_{name_part}"


def add_session_to_log(extracted_data: dict, source_file: str) -> bool:
    """Add extracted workout data to workout log."""
    workout_log = load_workout_log()

    # Build session object
    session_date = extracted_data.get("session_date")
    session_name = extracted_data.get("session_name")

    session = {
        "session_id": generate_session_id(session_date, session_name),
        "date": session_date,
        "date_confidence": "high" if session_date else "low",
        "source": f"screenshot_{Path(source_file).stem}",
    }

    if session_name:
        session["session_name"] = session_name

    if extracted_data.get("duration_minutes"):
        session["duration_minutes"] = extracted_data["duration_minutes"]

    if extracted_data.get("summary"):
        session["summary"] = extracted_data["summary"]

    session["exercises"] = extracted_data.get("exercises", [])

    # Check for duplicate sessions (same date and similar exercises)
    existing_ids = [s["session_id"] for s in workout_log["workout_sessions"]]
    if session["session_id"] in existing_ids:
        # Add timestamp to make unique
        session["session_id"] += f"_{datetime.now().strftime('%H%M%S')}"

    # Add to beginning of list (most recent first)
    workout_log["workout_sessions"].insert(0, session)

    save_workout_log(workout_log)
    return True


def process_screenshot(image_path: str, move_to_processed: bool = True) -> bool:
    """Process a single workout screenshot."""
    image_path = Path(image_path)

    if not image_path.exists():
        print(f"Error: File not found: {image_path}")
        return False

    print(f"Processing: {image_path.name}")

    # Initialize Anthropic client
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set")
        return False

    client = anthropic.Anthropic(api_key=api_key)

    # Extract data from image
    extracted_data = extract_workout_data(str(image_path), client)

    if not extracted_data:
        print(f"  Failed to extract data from {image_path.name}")
        return False

    # Show extracted data
    print(f"  Found: {len(extracted_data.get('exercises', []))} exercises")
    for ex in extracted_data.get('exercises', []):
        print(f"    - {ex.get('name')}: {ex.get('total_reps', '?')} reps")

    # Add to workout log
    if add_session_to_log(extracted_data, str(image_path)):
        print(f"  Added to workout_log.json")

    # Move to processed folder
    if move_to_processed:
        dest = PROCESSED_DIR / image_path.name
        shutil.move(str(image_path), str(dest))
        print(f"  Moved to processed/")

    return True


def process_folder(folder_path: str = None):
    """Process all unprocessed screenshots in folder."""
    folder = Path(folder_path) if folder_path else SCREENSHOT_DIR

    if not folder.exists():
        print(f"Error: Folder not found: {folder}")
        return

    # Find all image files not in processed folder
    image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
    images = [
        f for f in folder.iterdir()
        if f.suffix.lower() in image_extensions and f.is_file()
    ]

    if not images:
        print(f"No unprocessed images found in {folder}")
        return

    print(f"Found {len(images)} image(s) to process\n")

    success_count = 0
    for image in sorted(images):
        if process_screenshot(str(image)):
            success_count += 1
        print()

    print(f"Processed {success_count}/{len(images)} images successfully")


def main():
    if len(sys.argv) < 2:
        # Default: process all unprocessed in screenshot folder
        process_folder()
    elif sys.argv[1] == "--folder":
        folder = sys.argv[2] if len(sys.argv) > 2 else None
        process_folder(folder)
    else:
        # Process specific file
        process_screenshot(sys.argv[1])


if __name__ == "__main__":
    main()
