"""
Screenshot Processing Service
Extracts workout data from screenshots using Claude Vision API
"""
import os
import base64
import json
import re
import logging
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import or_

import anthropic

logger = logging.getLogger(__name__)
from rapidfuzz import fuzz, process

from app.models.exercise import Exercise
from app.models.workout import WorkoutSession, WorkoutExercise, Set, WeightUnit
from app.models.user import UserProfile, E1RMFormula
from app.api.exercises import EXERCISES_DATA
from app.core.e1rm import calculate_e1rm
from app.services.pr_detection import detect_and_create_prs
from app.services.xp_service import calculate_workout_xp, award_xp, get_or_create_user_progress
from app.services.achievement_service import check_and_unlock_achievements
from app.services.quest_service import update_quest_progress
from app.models.pr import PR


# Extraction prompt - handles both gym workout screenshots and WHOOP/activity screenshots
EXTRACTION_PROMPT = """Analyze this fitness screenshot and extract the data.

FIRST, determine the screenshot type:
1. "gym_workout" - Traditional weight training screenshot with exercises, sets, reps, weights
2. "whoop_activity" - WHOOP app or cardio/activity screenshot with metrics like strain, heart rate, calories, steps

Based on the type, return JSON in the appropriate format:

FOR GYM WORKOUT SCREENSHOTS (screenshot_type: "gym_workout"):
{
  "screenshot_type": "gym_workout",
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
          "is_warmup": true if this appears to be a warmup set
        }
      ],
      "total_reps": total reps for this exercise,
      "total_volume_lb": total volume (weight x reps) for this exercise
    }
  ]
}

FOR WHOOP/ACTIVITY SCREENSHOTS (screenshot_type: "whoop_activity"):
{
  "screenshot_type": "whoop_activity",
  "activity_type": "Activity name (e.g., 'TENNIS', 'RUNNING', 'CYCLING')",
  "session_date": "YYYY-MM-DD or null",
  "time_range": "Start to end time if visible (e.g., '7:03 PM to 8:46 PM')",
  "duration_minutes": number or null,
  "strain": activity strain score if visible (e.g., 14.6),
  "steps": step count if visible,
  "calories": calories burned if visible,
  "avg_hr": average heart rate in BPM if visible,
  "max_hr": max heart rate in BPM if visible,
  "source": "Data source if shown (e.g., 'VIA APPLE WATCH')",
  "heart_rate_zones": [
    {
      "zone": zone number (0-5),
      "bpm_range": "BPM range (e.g., '93-111')",
      "percentage": percentage of time in zone,
      "duration": "time in zone (e.g., '15:30')"
    }
  ]
}

Important:
- Convert all weights to pounds (lb) for gym workouts
- Extract the exact numbers shown - don't estimate
- Return ONLY valid JSON, no other text
- For WHOOP screenshots, extract all visible metrics even if some are missing"""


def get_media_type(filename: str) -> str:
    """Determine media type from filename extension."""
    ext = filename.lower().split('.')[-1] if '.' in filename else 'png'
    media_types = {
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'gif': 'image/gif',
        'webp': 'image/webp'
    }
    return media_types.get(ext, 'image/png')


def encode_image_bytes(image_data: bytes) -> str:
    """Encode image bytes to base64 string."""
    return base64.standard_b64encode(image_data).decode('utf-8')


def clean_json_response(response_text: str) -> str:
    """Clean up Claude's response to extract pure JSON."""
    text = response_text.strip()

    # Remove markdown code blocks if present
    if text.startswith('```'):
        lines = text.split('\n')
        # Remove first line (```json) and last line (```)
        text = '\n'.join(lines[1:-1] if lines[-1].strip() == '```' else lines[1:])

    return text.strip()


def build_exercise_candidates(db: Session, user_id: str) -> List[Tuple[str, str]]:
    """
    Build list of (name/alias, exercise_id) tuples for fuzzy matching.
    Includes both seeded exercises and user's custom exercises.
    """
    exercises = db.query(Exercise).filter(
        or_(
            Exercise.is_custom == False,
            Exercise.user_id == user_id
        )
    ).all()

    candidates = []

    # Add exercise names from database
    for ex in exercises:
        candidates.append((ex.name.lower(), ex.id))

    # Add aliases from EXERCISES_DATA
    exercise_id_map = {ex.name.lower(): ex.id for ex in exercises}

    for exercise_data in EXERCISES_DATA:
        name = exercise_data["name"].lower()
        if name in exercise_id_map:
            exercise_id = exercise_id_map[name]
            # Add all aliases
            for alias in exercise_data.get("aliases", []):
                candidates.append((alias.lower(), exercise_id))

    return candidates


def match_exercise_name(
    extracted_name: str,
    candidates: List[Tuple[str, str]],
    threshold: int = 70
) -> Tuple[Optional[str], Optional[str], int]:
    """
    Match extracted exercise name to database exercise using fuzzy matching.

    Returns:
        (exercise_id, matched_name, confidence_score)
    """
    if not candidates:
        return None, None, 0

    # Normalize the extracted name
    normalized_name = extracted_name.lower().strip()

    # Try exact match first
    for candidate_name, exercise_id in candidates:
        if candidate_name == normalized_name:
            return exercise_id, candidate_name.title(), 100

    # Fuzzy match
    candidate_names = [c[0] for c in candidates]
    result = process.extractOne(
        normalized_name,
        candidate_names,
        scorer=fuzz.ratio
    )

    if result and result[1] >= threshold:
        matched_name = result[0]
        # Find the exercise ID for this match
        for candidate_name, exercise_id in candidates:
            if candidate_name == matched_name:
                return exercise_id, matched_name.title(), result[1]

    return None, None, 0


async def extract_workout_from_screenshot(
    image_data: bytes,
    filename: str,
    db: Session,
    user_id: str
) -> Dict[str, Any]:
    """
    Process a workout screenshot and extract structured data.

    Args:
        image_data: Raw image bytes
        filename: Original filename (for media type detection)
        db: Database session
        user_id: Current user's ID for custom exercise matching

    Returns:
        Dict with extracted workout data and matched exercise IDs
    """
    logger.info(f"Processing screenshot: {filename}, size: {len(image_data)} bytes")

    # Check for API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set")
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    # Initialize Anthropic client
    client = anthropic.Anthropic(api_key=api_key)

    # Encode image
    image_base64 = encode_image_bytes(image_data)
    media_type = get_media_type(filename)

    # Call Claude Vision API
    try:
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
                                "data": image_base64
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
    except anthropic.APIError as e:
        logger.error(f"Claude API error: {e}")
        raise ValueError(f"Claude API error: {str(e)}")

    response_text = message.content[0].text
    logger.info(f"Claude response received, length: {len(response_text)}")
    cleaned_json = clean_json_response(response_text)

    # Parse JSON response
    try:
        extracted_data = json.loads(cleaned_json)
    except json.JSONDecodeError as e:
        # Log the actual response for debugging
        logger.error(f"Failed to parse JSON. Raw response: {response_text[:500]}")
        raise ValueError(f"Failed to parse Claude response as JSON: {e}. Response preview: {response_text[:200]}")

    # Check screenshot type
    screenshot_type = extracted_data.get("screenshot_type", "gym_workout")

    # Handle WHOOP/activity screenshots differently - no exercise matching needed
    if screenshot_type == "whoop_activity":
        return {
            "screenshot_type": "whoop_activity",
            "activity_type": extracted_data.get("activity_type"),
            "session_date": extracted_data.get("session_date"),
            "time_range": extracted_data.get("time_range"),
            "duration_minutes": extracted_data.get("duration_minutes"),
            "strain": extracted_data.get("strain"),
            "steps": extracted_data.get("steps"),
            "calories": extracted_data.get("calories"),
            "avg_hr": extracted_data.get("avg_hr"),
            "max_hr": extracted_data.get("max_hr"),
            "source": extracted_data.get("source"),
            "heart_rate_zones": extracted_data.get("heart_rate_zones") or [],
            "processing_confidence": "high",
            # Include empty exercises array for compatibility
            "exercises": [],
            "summary": {
                "tonnage_lb": 0,
                "total_reps": 0
            }
        }

    # For gym workouts, continue with exercise matching
    # Build exercise candidates for matching
    candidates = build_exercise_candidates(db, user_id)

    # Match exercise names to database exercises
    exercises_with_matches = []
    overall_confidence = "high"
    unmatched_count = 0

    # Use 'or []' to handle null values from Claude
    for exercise in (extracted_data.get("exercises") or []):
        exercise_name = exercise.get("name", "")
        exercise_id, matched_name, confidence = match_exercise_name(
            exercise_name, candidates
        )

        exercise_result = {
            **exercise,
            "matched_exercise_id": exercise_id,
            "matched_exercise_name": matched_name,
            "match_confidence": confidence
        }
        exercises_with_matches.append(exercise_result)

        if exercise_id is None:
            unmatched_count += 1

    # Determine overall processing confidence
    total_exercises = len(exercises_with_matches)
    if total_exercises > 0:
        if unmatched_count == 0:
            overall_confidence = "high"
        elif unmatched_count <= total_exercises / 3:
            overall_confidence = "medium"
        else:
            overall_confidence = "low"

    return {
        "screenshot_type": "gym_workout",
        "session_date": extracted_data.get("session_date"),
        "session_name": extracted_data.get("session_name"),
        "duration_minutes": extracted_data.get("duration_minutes"),
        "summary": extracted_data.get("summary"),
        "exercises": exercises_with_matches,
        "processing_confidence": overall_confidence
    }


def merge_extractions(extractions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merge multiple screenshot extractions into a single combined result.

    Args:
        extractions: List of extraction results from extract_workout_from_screenshot

    Returns:
        Merged extraction with all exercises combined
    """
    if not extractions:
        return {
            "session_date": None,
            "session_name": None,
            "duration_minutes": None,
            "summary": {"tonnage_lb": 0, "total_reps": 0},
            "exercises": [],
            "processing_confidence": "low"
        }

    if len(extractions) == 1:
        return extractions[0]

    # Take session info from first extraction that has it
    session_date = None
    session_name = None
    duration_minutes = None

    for ext in extractions:
        if not session_date and ext.get("session_date"):
            session_date = ext["session_date"]
        if not session_name and ext.get("session_name"):
            session_name = ext["session_name"]
        if not duration_minutes and ext.get("duration_minutes"):
            duration_minutes = ext["duration_minutes"]

    # Combine all exercises
    all_exercises = []
    for ext in extractions:
        all_exercises.extend(ext.get("exercises") or [])

    # Calculate combined summary
    total_tonnage = 0
    total_reps = 0
    for ext in extractions:
        summary = ext.get("summary", {})
        if summary:
            total_tonnage += summary.get("tonnage_lb", 0) or 0
            total_reps += summary.get("total_reps", 0) or 0

    # Determine overall confidence
    confidences = [ext.get("processing_confidence", "medium") for ext in extractions]
    if "low" in confidences:
        overall_confidence = "low"
    elif "medium" in confidences:
        overall_confidence = "medium"
    else:
        overall_confidence = "high"

    return {
        "session_date": session_date,
        "session_name": session_name,
        "duration_minutes": duration_minutes,
        "summary": {
            "tonnage_lb": total_tonnage,
            "total_reps": total_reps
        },
        "exercises": all_exercises,
        "processing_confidence": overall_confidence
    }


async def save_extracted_workout(
    db: Session,
    user_id: str,
    extraction_result: Dict[str, Any],
    session_date: Optional[datetime] = None,
    include_warmups: bool = True
) -> str:
    """
    Save extracted workout data as a new workout in the database.

    Args:
        db: Database session
        user_id: User ID
        extraction_result: Result from extract_workout_from_screenshot or merge_extractions
        session_date: Override session date (defaults to extracted date or today)
        include_warmups: Whether to include warmup sets

    Returns:
        Created workout ID
    """
    # Determine workout date
    if session_date:
        workout_date = session_date
    elif extraction_result.get("session_date"):
        try:
            workout_date = datetime.strptime(extraction_result["session_date"], "%Y-%m-%d")
        except (ValueError, TypeError):
            workout_date = datetime.utcnow()
    else:
        workout_date = datetime.utcnow()

    # Get user's e1RM formula preference
    user_profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    e1rm_formula = E1RMFormula.EPLEY
    if user_profile and user_profile.e1rm_formula:
        e1rm_formula = user_profile.e1rm_formula

    # Create workout session
    notes = f"Imported from screenshot"
    if extraction_result.get("session_name"):
        notes = f"{extraction_result['session_name']} - {notes}"

    workout_session = WorkoutSession(
        user_id=user_id,
        date=workout_date,
        duration_minutes=extraction_result.get("duration_minutes"),
        notes=notes
    )
    db.add(workout_session)
    db.flush()

    # Create exercises and sets
    order_index = 0
    for exercise_data in (extraction_result.get("exercises") or []):
        exercise_id = exercise_data.get("matched_exercise_id")

        # Skip exercises that weren't matched
        if not exercise_id:
            continue

        # Verify exercise exists
        exercise = db.query(Exercise).filter(Exercise.id == exercise_id).first()
        if not exercise:
            continue

        # Create workout exercise
        workout_exercise = WorkoutExercise(
            session_id=workout_session.id,
            exercise_id=exercise_id,
            order_index=order_index
        )
        db.add(workout_exercise)
        db.flush()
        order_index += 1

        # Create sets
        set_number = 1
        exercise_sets = []
        for set_data in (exercise_data.get("sets") or []):
            # Skip warmups if not included
            if not include_warmups and set_data.get("is_warmup", False):
                continue

            weight = set_data.get("weight_lb", 0)
            reps = set_data.get("reps", 1)
            num_sets = set_data.get("sets", 1)

            # Create multiple sets if sets > 1
            for _ in range(num_sets):
                if weight > 0 and reps > 0:
                    e1rm = calculate_e1rm(weight, reps, e1rm_formula)

                    set_obj = Set(
                        workout_exercise_id=workout_exercise.id,
                        weight=weight,
                        weight_unit=WeightUnit.LB,
                        reps=reps,
                        set_number=set_number,
                        e1rm=round(e1rm, 2)
                    )
                    db.add(set_obj)
                    exercise_sets.append(set_obj)
                    set_number += 1

        # Detect PRs for this exercise
        if exercise_sets:
            db.flush()
            detect_and_create_prs(db, user_id, workout_exercise, exercise_sets)

    db.commit()
    db.refresh(workout_session)

    # Calculate and award XP
    workout_prs = db.query(PR).filter(
        PR.user_id == user_id,
        PR.set_id.in_([s.id for we in workout_session.workout_exercises for s in we.sets])
    ).count()

    xp_result = calculate_workout_xp(db, workout_session, prs_achieved=workout_prs)
    award_xp(db, user_id, xp_result["xp_earned"], workout_date=workout_session.date)

    # Update progress stats
    progress = get_or_create_user_progress(db, user_id)
    progress.total_volume_lb += xp_result["total_volume"]
    progress.total_prs += workout_prs

    # Check achievements
    all_prs = db.query(PR).filter(PR.user_id == user_id).all()
    exercise_prs = {}
    for pr in all_prs:
        exercise_name = pr.exercise.name.lower() if pr.exercise else ""
        pr_weight = pr.weight if pr.weight is not None else pr.value
        if pr_weight is not None:
            if exercise_name not in exercise_prs or pr_weight > exercise_prs.get(exercise_name, 0):
                exercise_prs[exercise_name] = pr_weight

    achievement_context = {
        "workout_count": progress.total_workouts,
        "level": progress.level,
        "rank": progress.rank,
        "prs_count": progress.total_prs,
        "current_streak": progress.current_streak,
        "exercise_prs": exercise_prs
    }
    check_and_unlock_achievements(db, user_id, achievement_context)

    # Update quest progress
    update_quest_progress(db, user_id, workout_session)

    db.commit()

    return workout_session.id


async def save_whoop_activity(
    db: Session,
    user_id: str,
    extraction_result: dict,
    activity_date: Optional[datetime] = None
) -> Tuple[str, str]:
    """
    Save WHOOP activity data to DailyActivity table AND create a WorkoutSession
    so it appears in the quests calendar.

    Args:
        db: Database session
        user_id: User ID
        extraction_result: Extracted WHOOP data from screenshot
        activity_date: Optional override date

    Returns:
        Tuple of (activity_id, workout_id)
    """
    from app.models.activity import DailyActivity

    # Parse date from extraction or use provided/today
    if activity_date:
        date = activity_date.date() if hasattr(activity_date, 'date') else activity_date
        workout_datetime = activity_date if isinstance(activity_date, datetime) else datetime.combine(activity_date, datetime.min.time())
    elif extraction_result.get("session_date"):
        date = datetime.strptime(extraction_result["session_date"], "%Y-%m-%d").date()
        workout_datetime = datetime.strptime(extraction_result["session_date"], "%Y-%m-%d")
    else:
        date = datetime.now().date()
        workout_datetime = datetime.now()

    # Save to DailyActivity for metrics tracking
    existing = db.query(DailyActivity).filter(
        DailyActivity.user_id == user_id,
        DailyActivity.date == date,
        DailyActivity.source == "whoop_screenshot"
    ).first()

    if existing:
        if extraction_result.get("strain") is not None:
            existing.strain = extraction_result["strain"]
        if extraction_result.get("calories") is not None:
            existing.active_calories = extraction_result["calories"]
        if extraction_result.get("steps") is not None:
            existing.steps = extraction_result["steps"]
        if extraction_result.get("duration_minutes") is not None:
            existing.active_minutes = extraction_result["duration_minutes"]
        existing.updated_at = datetime.utcnow()
        activity_id = str(existing.id)
    else:
        activity = DailyActivity(
            user_id=user_id,
            date=date,
            source="whoop_screenshot",
            strain=extraction_result.get("strain"),
            active_calories=extraction_result.get("calories"),
            steps=extraction_result.get("steps"),
            active_minutes=extraction_result.get("duration_minutes")
        )
        db.add(activity)
        db.flush()
        activity_id = str(activity.id)

    # Create WorkoutSession so it appears in quests calendar
    activity_type = extraction_result.get("activity_type") or extraction_result.get("session_name") or "Activity"
    strain = extraction_result.get("strain")
    calories = extraction_result.get("calories")

    # Build notes with WHOOP metrics
    notes_parts = [f"{activity_type} - WHOOP Activity"]
    if strain:
        notes_parts.append(f"Strain: {strain}")
    if calories:
        notes_parts.append(f"Calories: {calories}")
    if extraction_result.get("time_range"):
        notes_parts.append(f"Time: {extraction_result['time_range']}")
    notes = " | ".join(notes_parts)

    workout_session = WorkoutSession(
        user_id=user_id,
        date=workout_datetime,
        duration_minutes=extraction_result.get("duration_minutes"),
        notes=notes
    )
    db.add(workout_session)
    db.flush()
    workout_id = str(workout_session.id)

    db.commit()
    return activity_id, workout_id
