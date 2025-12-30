"""Screenshot-based activity data extraction using Claude Vision."""

import base64
import json
import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from ..models.activity import (
    ActivitySource,
    CardioActivity,
    CardioWorkoutType,
    DailyActivityEntry,
)


class ScreenshotExtractionResult(BaseModel):
    """Result of screenshot extraction."""

    success: bool
    entry: Optional[DailyActivityEntry] = None
    raw_response: Optional[str] = None
    error: Optional[str] = None
    confidence: float = 0.0


WHOOP_EXTRACTION_PROMPT = """Analyze this Whoop screenshot and extract activity/health metrics.
Return ONLY a valid JSON object with these fields (use null for any not visible):

{
    "date": "YYYY-MM-DD",
    "strain": 0.0,
    "recovery_score": 0,
    "hrv": 0,
    "resting_heart_rate": 0,
    "sleep_hours": 0.0,
    "sleep_quality": 0,
    "total_calories": 0,
    "active_calories": 0,
    "activities": [
        {
            "activity_type": "string",
            "duration_minutes": 0,
            "calories_burned": 0,
            "avg_heart_rate": 0,
            "max_heart_rate": 0
        }
    ]
}

Valid activity_type values: walking, running, cycling, swimming, hiit, rowing, elliptical, strength, yoga, other

Only include fields you can clearly see. Be precise with numbers.
Return ONLY the JSON, no other text."""

APPLE_FITNESS_PROMPT = """Analyze this Apple Fitness/Activity screenshot and extract metrics.
Return ONLY a valid JSON object with these fields (use null for any not visible):

{
    "date": "YYYY-MM-DD",
    "move_calories": 0,
    "exercise_minutes": 0,
    "stand_hours": 0,
    "steps": 0,
    "total_calories": 0,
    "active_calories": 0,
    "activities": [
        {
            "activity_type": "string",
            "duration_minutes": 0,
            "calories_burned": 0,
            "distance_miles": 0.0,
            "avg_heart_rate": 0
        }
    ]
}

Valid activity_type values: walking, running, cycling, swimming, hiit, rowing, elliptical, strength, yoga, other

Focus on activity rings and workout summaries. Be precise with numbers.
Return ONLY the JSON, no other text."""

GENERIC_DETECTION_PROMPT = """What fitness tracker app is shown in this screenshot?
Answer with ONLY one of these words:
- whoop
- apple_fitness
- garmin
- fitbit
- unknown"""


def detect_source(image_path: Path, api_key: Optional[str] = None) -> ActivitySource:
    """
    Auto-detect the fitness tracker source from a screenshot.

    Args:
        image_path: Path to the screenshot image
        api_key: Anthropic API key (uses ANTHROPIC_API_KEY env var if not provided)

    Returns:
        Detected ActivitySource
    """
    try:
        from anthropic import Anthropic
    except ImportError:
        raise ImportError("anthropic package required: pip install anthropic")

    client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    image_data, media_type = _load_image(image_path)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=50,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data,
                        },
                    },
                    {"type": "text", "text": GENERIC_DETECTION_PROMPT},
                ],
            }
        ],
    )

    result = response.content[0].text.strip().lower()

    source_map = {
        "whoop": ActivitySource.WHOOP,
        "apple_fitness": ActivitySource.APPLE_FITNESS,
        "apple": ActivitySource.APPLE_FITNESS,
        "garmin": ActivitySource.GARMIN,
        "fitbit": ActivitySource.FITBIT,
    }

    return source_map.get(result, ActivitySource.MANUAL)


def extract_from_screenshot(
    image_path: Path,
    source: Optional[ActivitySource] = None,
    date_override: Optional[date] = None,
    api_key: Optional[str] = None,
) -> ScreenshotExtractionResult:
    """
    Extract activity data from a fitness tracker screenshot.

    Args:
        image_path: Path to the screenshot image
        source: The fitness tracker source (auto-detected if not provided)
        date_override: Override the date (uses today if not in screenshot)
        api_key: Anthropic API key (uses ANTHROPIC_API_KEY env var if not provided)

    Returns:
        ScreenshotExtractionResult with extracted data or error
    """
    try:
        from anthropic import Anthropic
    except ImportError:
        return ScreenshotExtractionResult(
            success=False,
            error="anthropic package required: pip install anthropic",
        )

    if not image_path.exists():
        return ScreenshotExtractionResult(
            success=False,
            error=f"Image file not found: {image_path}",
        )

    # Auto-detect source if not provided
    if source is None:
        source = detect_source(image_path, api_key)

    client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    try:
        image_data, media_type = _load_image(image_path)
    except Exception as e:
        return ScreenshotExtractionResult(
            success=False,
            error=f"Failed to load image: {e}",
        )

    # Select prompt based on source
    if source == ActivitySource.WHOOP:
        prompt = WHOOP_EXTRACTION_PROMPT
    elif source == ActivitySource.APPLE_FITNESS:
        prompt = APPLE_FITNESS_PROMPT
    else:
        # Use a generic prompt for other sources
        prompt = WHOOP_EXTRACTION_PROMPT  # Fallback to Whoop format

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
    except Exception as e:
        return ScreenshotExtractionResult(
            success=False,
            error=f"API call failed: {e}",
        )

    raw_response = response.content[0].text

    # Parse JSON response
    try:
        data = _parse_json_response(raw_response)
    except Exception as e:
        return ScreenshotExtractionResult(
            success=False,
            raw_response=raw_response,
            error=f"Failed to parse response as JSON: {e}",
        )

    # Build DailyActivityEntry
    try:
        entry = _build_activity_entry(data, source, date_override)
        entry.raw_ocr_text = raw_response

        return ScreenshotExtractionResult(
            success=True,
            entry=entry,
            raw_response=raw_response,
            confidence=0.8,  # Could be improved with more sophisticated confidence scoring
        )
    except Exception as e:
        return ScreenshotExtractionResult(
            success=False,
            raw_response=raw_response,
            error=f"Failed to build activity entry: {e}",
        )


def _load_image(image_path: Path) -> tuple[str, str]:
    """Load and encode an image file."""
    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    suffix = image_path.suffix.lower()
    media_type_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    media_type = media_type_map.get(suffix, "image/png")

    return image_data, media_type


def _parse_json_response(response: str) -> dict:
    """Parse JSON from API response, handling markdown code blocks."""
    text = response.strip()

    # Remove markdown code blocks if present
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]

    return json.loads(text.strip())


def _build_activity_entry(
    data: dict,
    source: ActivitySource,
    date_override: Optional[date],
) -> DailyActivityEntry:
    """Build a DailyActivityEntry from parsed JSON data."""
    # Parse date
    entry_date = date_override
    if not entry_date and data.get("date"):
        try:
            entry_date = date.fromisoformat(data["date"])
        except ValueError:
            entry_date = date.today()
    if not entry_date:
        entry_date = date.today()

    # Parse activities
    activities = []
    for a_data in data.get("activities", []) or []:
        if not a_data:
            continue

        activity_type_str = a_data.get("activity_type", "other")
        try:
            activity_type = CardioWorkoutType(activity_type_str.lower())
        except ValueError:
            activity_type = CardioWorkoutType.OTHER

        distance = a_data.get("distance_miles")
        if distance is not None:
            distance = Decimal(str(distance))

        activities.append(
            CardioActivity(
                activity_type=activity_type,
                duration_minutes=a_data.get("duration_minutes", 0) or 0,
                calories_burned=a_data.get("calories_burned"),
                avg_heart_rate=a_data.get("avg_heart_rate"),
                max_heart_rate=a_data.get("max_heart_rate"),
                distance_miles=distance,
            )
        )

    return DailyActivityEntry(
        date=entry_date,
        source=source,
        steps=data.get("steps"),
        total_calories=data.get("total_calories"),
        active_calories=data.get("active_calories"),
        active_minutes=data.get("active_minutes"),
        strain=data.get("strain"),
        recovery_score=data.get("recovery_score"),
        hrv=data.get("hrv"),
        resting_heart_rate=data.get("resting_heart_rate"),
        sleep_hours=data.get("sleep_hours"),
        sleep_quality=data.get("sleep_quality"),
        exercise_minutes=data.get("exercise_minutes"),
        stand_hours=data.get("stand_hours"),
        move_calories=data.get("move_calories"),
        activities=activities,
    )
