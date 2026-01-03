"""
Screenshot Processing API endpoints
Handles workout screenshot uploads and Claude Vision extraction
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date, datetime
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.screenshot import (
    ScreenshotProcessResponse, ScreenshotBatchResponse,
    ExtractedExercise, ExtractedSet
)
from app.services.screenshot_service import (
    extract_workout_from_screenshot,
    save_extracted_workout,
    merge_extractions
)

router = APIRouter()

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
    # Validate content type
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type: {file.content_type}. Allowed types: {', '.join(ALLOWED_CONTENT_TYPES)}"
        )

    # Read file content
    content = await file.read()

    # Validate file size
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024 * 1024)} MB"
        )

    # Process the screenshot
    try:
        result = await extract_workout_from_screenshot(
            image_data=content,
            filename=file.filename or "screenshot.png",
            db=db,
            user_id=current_user.id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process screenshot: {str(e)}"
        )

    # Convert to response model
    exercises = []
    for ex in result.get("exercises", []):
        sets = []
        for s in ex.get("sets", []):
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

    # Auto-save workout if requested
    workout_id = None
    workout_saved = False
    if save_workout:
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
            # Don't fail the whole request if save fails
            # Just return without workout_id
            pass

    return ScreenshotProcessResponse(
        session_date=result.get("session_date"),
        session_name=result.get("session_name"),
        duration_minutes=result.get("duration_minutes"),
        summary=result.get("summary"),
        exercises=exercises,
        processing_confidence=result.get("processing_confidence", "medium"),
        workout_id=workout_id,
        workout_saved=workout_saved
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

    # Convert exercises to response model
    exercises = []
    for ex in merged.get("exercises", []):
        sets = []
        for s in ex.get("sets", []):
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

    # Auto-save workout if requested
    workout_id = None
    workout_saved = False
    if save_workout:
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
            # Don't fail if save fails
            pass

    return ScreenshotBatchResponse(
        screenshots_processed=len(files),
        session_date=merged.get("session_date"),
        session_name=merged.get("session_name"),
        duration_minutes=merged.get("duration_minutes"),
        summary=merged.get("summary"),
        exercises=exercises,
        processing_confidence=merged.get("processing_confidence", "medium"),
        workout_id=workout_id,
        workout_saved=workout_saved
    )
