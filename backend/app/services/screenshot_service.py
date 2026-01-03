"""
Screenshot Processing Service
Extracts workout data from screenshots using Claude Vision API
"""
import os
import base64
import json
import re
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import or_

import anthropic
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


# Extraction prompt - proven to work well with workout screenshots
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
    # Check for API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    # Initialize Anthropic client
    client = anthropic.Anthropic(api_key=api_key)

    # Encode image
    image_base64 = encode_image_bytes(image_data)
    media_type = get_media_type(filename)

    # Call Claude Vision API
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

    response_text = message.content[0].text
    cleaned_json = clean_json_response(response_text)

    # Parse JSON response
    try:
        extracted_data = json.loads(cleaned_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse Claude response as JSON: {e}")

    # Build exercise candidates for matching
    candidates = build_exercise_candidates(db, user_id)

    # Match exercise names to database exercises
    exercises_with_matches = []
    overall_confidence = "high"
    unmatched_count = 0

    for exercise in extracted_data.get("exercises", []):
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
        all_exercises.extend(ext.get("exercises", []))

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
    for exercise_data in extraction_result.get("exercises", []):
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
        for set_data in exercise_data.get("sets", []):
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
