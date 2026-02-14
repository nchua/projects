"""
Screenshot Processing API endpoints
Handles workout screenshot uploads and Claude Vision extraction
"""
import logging
import traceback
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import date, datetime, timedelta
from app.core.database import get_db
from app.core.config import settings
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.screenshot_usage import ScreenshotUsage

logger = logging.getLogger(__name__)

# Rate limiting constants
DAILY_SCREENSHOT_LIMIT = 20
COOLDOWN_SECONDS = 10
from app.schemas.screenshot import (
    ScreenshotProcessResponse, ScreenshotBatchResponse,
    ExtractedExercise, ExtractedSet, HeartRateZone
)
from app.services.screenshot_service import (
    extract_workout_from_screenshot,
    save_extracted_workout,
    merge_extractions,
    save_whoop_activity
)

router = APIRouter()


def _check_screenshot_rate_limit(db: Session, user_id: str, screenshot_count: int = 1) -> None:
    """Check rate limits for screenshot processing. Raises HTTPException if exceeded."""
    if not settings.SCREENSHOT_PROCESSING_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Screenshot scanning temporarily unavailable"
        )

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # Check daily limit
    today_usage = db.query(func.sum(ScreenshotUsage.screenshots_count)).filter(
        ScreenshotUsage.user_id == user_id,
        ScreenshotUsage.created_at >= today_start
    ).scalar() or 0

    if today_usage + screenshot_count > DAILY_SCREENSHOT_LIMIT:
        resets_at = today_start + timedelta(days=1)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily limit reached. You've used {today_usage}/{DAILY_SCREENSHOT_LIMIT} screenshots today.",
            headers={"Retry-After": str(int((resets_at - datetime.utcnow()).total_seconds()))}
        )

    # Check cooldown (10 seconds between requests)
    last_usage = db.query(ScreenshotUsage).filter(
        ScreenshotUsage.user_id == user_id
    ).order_by(ScreenshotUsage.created_at.desc()).first()

    if last_usage and (datetime.utcnow() - last_usage.created_at).total_seconds() < COOLDOWN_SECONDS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Please wait a few seconds between screenshot requests.",
            headers={"Retry-After": str(COOLDOWN_SECONDS)}
        )


def _record_screenshot_usage(db: Session, user_id: str, count: int = 1) -> None:
    """Record screenshot usage for rate limiting."""
    usage = ScreenshotUsage(user_id=user_id, screenshots_count=count)
    db.add(usage)
    db.commit()


# Allowed image types
ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp"
}

# Max file size (10 MB)
MAX_FILE_SIZE = 10 * 1024 * 1024


@router.post("/process", response_model=ScreenshotProcessResponse)
@router.post("/process/", response_model=ScreenshotProcessResponse)
async def process_screenshot(
    file: UploadFile = File(..., description="Workout screenshot image"),
    save_workout: bool = Form(default=False, description="Auto-save as workout"),
    session_date: Optional[str] = Form(default=None, description="Override session date (YYYY-MM-DD)"),
    include_warmups: bool = Form(default=True, description="Include warmup sets"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Process a workout screenshot and extract structured data.

    Accepts an image file (PNG, JPEG, GIF, WebP) and uses Claude Vision
    to extract workout data including exercises, sets, reps, and weights.
    Exercise names are fuzzy-matched to the exercise library.

    Args:
        file: Uploaded image file
        save_workout: If True, auto-save extracted data as a workout
        session_date: Override session date (YYYY-MM-DD format)
        include_warmups: Include warmup sets when saving
        current_user: Authenticated user
        db: Database session

    Returns:
        Extracted workout data with matched exercise IDs

    Raises:
        HTTPException: If file type is invalid, file is too large, or processing fails
    """
    # Rate limiting check
    _check_screenshot_rate_limit(db, current_user.id, screenshot_count=1)

    import sys
    # Read first few bytes to check actual file format
    first_bytes = await file.read(16)
    await file.seek(0)  # Reset to beginning
    hex_preview = first_bytes.hex()[:32]
    sys.stderr.write(f"SCREENSHOT: filename={file.filename}, content_type={file.content_type}, first_bytes={hex_preview}\n")
    sys.stderr.flush()
    logger.info(f"Screenshot process request received: filename={file.filename}, content_type={file.content_type}")

    # Validate content type
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        logger.warning(f"Invalid content type: {file.content_type}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type: {file.content_type}. Allowed types: {', '.join(ALLOWED_CONTENT_TYPES)}"
        )

    # Read file content
    content = await file.read()
    logger.info(f"File read successfully, size: {len(content)} bytes")

    # Validate file size
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024 * 1024)} MB"
        )

    # Process the screenshot
    try:
        logger.info("Calling extract_workout_from_screenshot...")
        result = await extract_workout_from_screenshot(
            image_data=content,
            filename=file.filename or "screenshot.png",
            db=db,
            user_id=current_user.id
        )
        logger.info(f"Extraction complete, screenshot_type: {result.get('screenshot_type')}")
        _record_screenshot_usage(db, current_user.id, count=1)
    except ValueError as e:
        logger.error(f"ValueError during extraction: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error during extraction: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process screenshot: {str(e)}"
        )

    # Get screenshot type
    screenshot_type = result.get("screenshot_type", "gym_workout")

    # Convert exercises to response model (for gym workouts)
    exercises = []
    for ex in (result.get("exercises") or []):
        sets = []
        for s in (ex.get("sets") or []):
            sets.append(ExtractedSet(
                weight_lb=s.get("weight_lb", 0),
                reps=s.get("reps", 0),
                sets=s.get("sets", 1),
                is_warmup=s.get("is_warmup", False)
            ))

        exercises.append(ExtractedExercise(
            name=ex.get("name", "Unknown"),
            equipment=ex.get("equipment"),
            variation=ex.get("variation"),
            sets=sets,
            total_reps=ex.get("total_reps"),
            total_volume_lb=ex.get("total_volume_lb"),
            matched_exercise_id=ex.get("matched_exercise_id"),
            matched_exercise_name=ex.get("matched_exercise_name"),
            match_confidence=ex.get("match_confidence")
        ))

    # Convert heart rate zones for WHOOP screenshots
    heart_rate_zones = []
    for zone in (result.get("heart_rate_zones") or []):
        heart_rate_zones.append(HeartRateZone(
            zone=zone.get("zone"),
            bpm_range=zone.get("bpm_range"),
            percentage=zone.get("percentage"),
            duration=zone.get("duration")
        ))

    # Auto-save workout if requested (only for gym workouts with matched exercises)
    workout_id = None
    workout_saved = False
    if save_workout and screenshot_type == "gym_workout" and exercises:
        try:
            # Parse session_date if provided
            parsed_date = None
            if session_date:
                parsed_date = datetime.strptime(session_date, "%Y-%m-%d")

            workout_id = await save_extracted_workout(
                db=db,
                user_id=current_user.id,
                extraction_result=result,
                session_date=parsed_date,
                include_warmups=include_warmups
            )
            workout_saved = True
        except Exception as e:
            # Log full error details for debugging
            logger.error(f"[SINGLE SAVE ERROR] Failed to save workout: {str(e)}")
            logger.error(f"[SINGLE SAVE ERROR] Traceback:\n{traceback.format_exc()}")
            # Don't fail the whole request - still return extraction data

    # Auto-save WHOOP activity data (also creates a WorkoutSession for calendar)
    activity_id = None
    activity_saved = False
    if screenshot_type == "whoop_activity":
        try:
            # Parse session_date if provided (for manual date override)
            parsed_date = None
            if session_date:
                parsed_date = datetime.strptime(session_date, "%Y-%m-%d")

            activity_id, whoop_workout_id = await save_whoop_activity(
                db=db,
                user_id=current_user.id,
                extraction_result=result,
                activity_date=parsed_date
            )
            activity_saved = True
            # Set workout_id so it shows in quests calendar
            workout_id = whoop_workout_id
            workout_saved = True
        except Exception as e:
            # Log full error details for debugging
            logger.error(f"[WHOOP SAVE ERROR] Failed to save activity: {str(e)}")
            logger.error(f"[WHOOP SAVE ERROR] Traceback:\n{traceback.format_exc()}")

    return ScreenshotProcessResponse(
        screenshot_type=screenshot_type,
        session_date=result.get("session_date"),
        session_name=result.get("session_name") or result.get("activity_type"),
        duration_minutes=result.get("duration_minutes"),
        summary=result.get("summary"),
        exercises=exercises,
        processing_confidence=result.get("processing_confidence", "medium"),
        workout_id=workout_id,
        workout_saved=workout_saved,
        activity_id=activity_id,
        activity_saved=activity_saved,
        # WHOOP-specific fields
        activity_type=result.get("activity_type"),
        time_range=result.get("time_range"),
        strain=result.get("strain"),
        steps=result.get("steps"),
        calories=result.get("calories"),
        avg_hr=result.get("avg_hr"),
        max_hr=result.get("max_hr"),
        source=result.get("source"),
        heart_rate_zones=heart_rate_zones
    )


@router.post("/process/batch", response_model=ScreenshotBatchResponse)
@router.post("/process/batch/", response_model=ScreenshotBatchResponse)
async def process_screenshots_batch(
    files: List[UploadFile] = File(..., description="Multiple workout screenshot images"),
    save_workout: bool = Form(default=True, description="Auto-save as workout"),
    session_date: Optional[str] = Form(default=None, description="Override session date (YYYY-MM-DD)"),
    include_warmups: bool = Form(default=True, description="Include warmup sets"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Process multiple workout screenshots and combine into a single workout.

    Accepts multiple image files and uses Claude Vision to extract workout data
    from each. Results are merged into a single combined workout with all exercises.

    Args:
        files: List of uploaded image files
        save_workout: If True, auto-save combined data as a workout (default: True)
        session_date: Override session date (YYYY-MM-DD format)
        include_warmups: Include warmup sets when saving
        current_user: Authenticated user
        db: Database session

    Returns:
        Combined workout data with all extracted exercises

    Raises:
        HTTPException: If file type is invalid, file is too large, or processing fails
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided"
        )

    # Rate limiting check
    _check_screenshot_rate_limit(db, current_user.id, screenshot_count=len(files))

    if len(files) > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 10 screenshots per batch"
        )

    # Process each screenshot
    extractions = []
    for file in files:
        # Validate content type
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file type for {file.filename}: {file.content_type}"
            )

        # Read file content
        content = await file.read()

        # Validate file size
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File too large: {file.filename}"
            )

        # Process the screenshot
        try:
            result = await extract_workout_from_screenshot(
                image_data=content,
                filename=file.filename or "screenshot.png",
                db=db,
                user_id=current_user.id
            )
            extractions.append(result)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to process {file.filename}: {str(e)}"
            )

    # Merge all extractions
    merged = merge_extractions(extractions)

    # Record usage after successful processing
    _record_screenshot_usage(db, current_user.id, count=len(files))

    # Get screenshot type
    screenshot_type = merged.get("screenshot_type", "gym_workout")

    # Convert exercises to response model
    exercises = []
    for ex in (merged.get("exercises") or []):
        sets = []
        for s in (ex.get("sets") or []):
            sets.append(ExtractedSet(
                weight_lb=s.get("weight_lb", 0),
                reps=s.get("reps", 0),
                sets=s.get("sets", 1),
                is_warmup=s.get("is_warmup", False)
            ))

        exercises.append(ExtractedExercise(
            name=ex.get("name", "Unknown"),
            equipment=ex.get("equipment"),
            variation=ex.get("variation"),
            sets=sets,
            total_reps=ex.get("total_reps"),
            total_volume_lb=ex.get("total_volume_lb"),
            matched_exercise_id=ex.get("matched_exercise_id"),
            matched_exercise_name=ex.get("matched_exercise_name"),
            match_confidence=ex.get("match_confidence")
        ))

    # Convert heart rate zones for WHOOP screenshots
    heart_rate_zones = []
    for zone in (merged.get("heart_rate_zones") or []):
        heart_rate_zones.append(HeartRateZone(
            zone=zone.get("zone"),
            bpm_range=zone.get("bpm_range"),
            percentage=zone.get("percentage"),
            duration=zone.get("duration")
        ))

    # Auto-save workout if requested (only for gym workouts)
    workout_id = None
    workout_saved = False
    if save_workout and screenshot_type == "gym_workout" and exercises:
        try:
            parsed_date = None
            if session_date:
                parsed_date = datetime.strptime(session_date, "%Y-%m-%d")

            workout_id = await save_extracted_workout(
                db=db,
                user_id=current_user.id,
                extraction_result=merged,
                session_date=parsed_date,
                include_warmups=include_warmups
            )
            workout_saved = True
        except Exception as e:
            # Log full error details for debugging
            logger.error(f"[BATCH SAVE ERROR] Failed to save workout: {str(e)}")
            logger.error(f"[BATCH SAVE ERROR] Traceback:\n{traceback.format_exc()}")
            logger.error(f"[BATCH SAVE ERROR] Merged data keys: {list(merged.keys())}")
            logger.error(f"[BATCH SAVE ERROR] Exercise count: {len(merged.get('exercises', []))}")
            # Log each exercise for debugging
            for i, ex in enumerate(merged.get("exercises", [])):
                logger.error(f"[BATCH SAVE ERROR] Exercise {i}: name={ex.get('name')}, matched_id={ex.get('matched_exercise_id')}, sets={len(ex.get('sets', []))}")
            # Don't fail the whole request - still return extraction data

    # Auto-save WHOOP activity data (also creates a WorkoutSession for calendar)
    activity_id = None
    activity_saved = False
    if screenshot_type == "whoop_activity":
        try:
            # Parse session_date if provided (for manual date override)
            parsed_activity_date = None
            if session_date:
                parsed_activity_date = datetime.strptime(session_date, "%Y-%m-%d")

            activity_id, whoop_workout_id = await save_whoop_activity(
                db=db,
                user_id=current_user.id,
                extraction_result=merged,
                activity_date=parsed_activity_date
            )
            activity_saved = True
            # Set workout_id so it shows in quests calendar
            workout_id = whoop_workout_id
            workout_saved = True
        except Exception as e:
            # Log full error details for debugging
            logger.error(f"[BATCH WHOOP SAVE ERROR] Failed to save activity: {str(e)}")
            logger.error(f"[BATCH WHOOP SAVE ERROR] Traceback:\n{traceback.format_exc()}")

    return ScreenshotBatchResponse(
        screenshots_processed=len(files),
        screenshot_type=screenshot_type,
        session_date=merged.get("session_date"),
        session_name=merged.get("session_name") or merged.get("activity_type"),
        duration_minutes=merged.get("duration_minutes"),
        summary=merged.get("summary"),
        exercises=exercises,
        processing_confidence=merged.get("processing_confidence", "medium"),
        workout_id=workout_id,
        workout_saved=workout_saved,
        activity_id=activity_id,
        activity_saved=activity_saved,
        # WHOOP-specific fields
        activity_type=merged.get("activity_type"),
        time_range=merged.get("time_range"),
        strain=merged.get("strain"),
        steps=merged.get("steps"),
        calories=merged.get("calories"),
        avg_hr=merged.get("avg_hr"),
        max_hr=merged.get("max_hr"),
        source=merged.get("source"),
        heart_rate_zones=heart_rate_zones
    )
