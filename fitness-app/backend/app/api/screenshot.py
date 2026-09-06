"""
Screenshot Processing API endpoints
Handles workout screenshot uploads and Claude Vision extraction
"""
import logging
import traceback
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

import anthropic
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.core.dependencies import get_current_user
from app.core.utils import ensure_utc
from app.models.scan_balance import ScanBalance
from app.models.screenshot_usage import ScreenshotUsage
from app.models.user import User

logger = logging.getLogger(__name__)

# Rate-limit defaults live on ``settings`` (DAILY_SCREENSHOT_LIMIT,
# COOLDOWN_SECONDS, FREE_MONTHLY_SCANS) and are overridable per user through
# entitlements — see ``entitlement_service.effective_limits`` (spec §6.1).
from app.schemas.screenshot import (
    ActivitySaveRequest,
    ActivitySaveResponse,
    ExtractedExercise,
    ExtractedSet,
    HeartRateZone,
    ScreenshotBatchResponse,
    ScreenshotProcessResponse,
)
from app.services import entitlement_service
from app.services.entitlement_service import ScanLimits
from app.services.screenshot_service import (
    extract_workout_from_screenshot,
    merge_extractions,
    save_extracted_workout,
    save_whoop_activity,
)

router = APIRouter()


def _refund_scan_credits(db: Session, user_id: str, count: int) -> None:
    """
    Compensating refund for batch failures. Skipped for unlimited users.

    Runs in its OWN short transaction with a fresh FOR UPDATE lock — the
    caller has already committed the original deduction, so this must stand
    alone. Callers should wrap invocations in a try/except because by the
    time we refund the user has already received their HTTP response and we
    must not raise.
    """
    if count <= 0:
        return
    balance = db.query(ScanBalance).filter(ScanBalance.user_id == user_id).with_for_update().first()
    if balance and not balance.has_unlimited:
        balance.scan_credits = balance.scan_credits + count
        db.commit()


def _refund_scan_credits_safe(
    db_factory,
    user_id: str,
    count: int,
    *,
    max_attempts: int = 2,
) -> bool:
    """
    Best-effort refund that never raises.

    Opens a FRESH DB session per attempt via `db_factory()` so a poisoned
    request session doesn't cascade into the refund path. On failure we log
    at ERROR level with a REFUND FAILED marker so the over-bill is visible
    in logs / alerting. We do not re-raise: by the time this runs the user
    already has their HTTP response and we'd rather fail a refund than
    convert (say) a 504 into a 500.

    Returns True if the refund committed, False if all attempts failed.
    """
    if count <= 0:
        return True

    last_error: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        fresh_db: Optional[Session] = None
        try:
            fresh_db = db_factory()
            _refund_scan_credits(fresh_db, user_id, count)
            return True
        except Exception as e:  # noqa: BLE001 - best-effort, must not raise
            last_error = e
            logger.warning(
                "[REFUND RETRY] attempt %d/%d failed for user_id=%s count=%d: %s",
                attempt,
                max_attempts,
                user_id,
                count,
                e,
            )
            if fresh_db is not None:
                try:
                    fresh_db.rollback()
                except Exception:  # noqa: BLE001
                    pass
        finally:
            if fresh_db is not None:
                try:
                    fresh_db.close()
                except Exception:  # noqa: BLE001
                    pass

    logger.error(
        "[REFUND FAILED] user_id=%s count=%d attempts=%d last_error=%r — "
        "user is over-billed; manual credit adjustment required",
        user_id,
        count,
        max_attempts,
        last_error,
    )
    return False


def _assert_daily_cap(db: Session, user_id: str, screenshot_count: int, daily_limit: int) -> None:
    """Raise 429 if ``screenshot_count`` more scans would exceed today's hard cap."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_usage = db.query(func.sum(ScreenshotUsage.screenshots_count)).filter(
        ScreenshotUsage.user_id == user_id,
        ScreenshotUsage.created_at >= today_start
    ).scalar() or 0

    if today_usage + screenshot_count > daily_limit:
        resets_at = today_start + timedelta(days=1)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily limit reached. You've used {today_usage}/{daily_limit} screenshots today.",
            headers={"Retry-After": str(int((resets_at - datetime.now(timezone.utc)).total_seconds()))}
        )


def _check_screenshot_rate_limit(
    db: Session,
    user_id: str,
    screenshot_count: int = 1,
    *,
    limits: Optional[ScanLimits] = None,
) -> None:
    """
    Check non-monetary rate limits (feature flag, daily abuse cap, cooldown).

    Does NOT check or deduct scan credits — that happens atomically in
    `_reserve_scan_credits`, which re-checks the daily cap under the row
    lock (the pre-check here is a fast fail). Raises HTTPException if
    limits are exceeded.
    """
    if not settings.SCREENSHOT_PROCESSING_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Screenshot scanning temporarily unavailable"
        )

    if limits is None:
        limits = entitlement_service.effective_limits(db, user_id)

    # Check daily abuse limit (hard cap regardless of payment)
    _assert_daily_cap(db, user_id, screenshot_count, limits.daily_limit)

    # Check cooldown between requests
    last_usage = db.query(ScreenshotUsage).filter(
        ScreenshotUsage.user_id == user_id
    ).order_by(ScreenshotUsage.created_at.desc()).first()

    if last_usage and (datetime.now(timezone.utc) - ensure_utc(last_usage.created_at)).total_seconds() < limits.cooldown_seconds:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Please wait a few seconds between screenshot requests.",
            headers={"Retry-After": str(limits.cooldown_seconds)}
        )


def _reserve_scan_credits(
    db: Session,
    user_id: str,
    count: int = 1,
    *,
    limits: Optional[ScanLimits] = None,
) -> bool:
    """
    Atomically check balance and reserve (deduct) `count` credits.

    Uses SELECT ... FOR UPDATE to lock the ScanBalance row so two concurrent
    requests cannot both observe sufficient credits and each deduct. On
    Postgres this serializes the read/modify/write. On SQLite the lock is a
    no-op at the row level, but the single in-process transaction still
    enforces ordering via Python's GIL + SQLite's database-level locking.

    The caller is responsible for committing (on success) or rolling back
    (on failure) the surrounding transaction. If rollback occurs, the
    deduction is automatically reversed.

    Returns:
        True if credits were reserved (including unlimited users).
        False if the user has insufficient credits — caller should 402.
    """
    # Resolve per-user limits BEFORE taking the lock (one indexed query; a
    # stale read costs at most one scan). Ensure a balance row exists before
    # taking the row lock — creation commits on its own (once per user).
    if limits is None:
        limits = entitlement_service.effective_limits(db, user_id)
    entitlement_service.get_or_create_balance(db, user_id, free_monthly=limits.free_monthly)

    # Re-query under row lock to prevent read/modify/write race. The monthly
    # reset is applied INSIDE this locked section so two concurrent
    # reset-time requests cannot each commit a separate +FREE_MONTHLY_SCANS
    # (which would double-credit the user).
    locked_balance = (
        db.query(ScanBalance)
        .filter(ScanBalance.user_id == user_id)
        .with_for_update()
        .first()
    )
    if locked_balance is None:
        # Should not happen — get_or_create_balance just created it.
        return False

    # Authoritative daily-cap check under the lock: two concurrent scans
    # can both pass the unlocked pre-check in _check_screenshot_rate_limit.
    _assert_daily_cap(db, user_id, count, limits.daily_limit)

    # Apply monthly reset if due. Mutates the locked row without committing;
    # the same transaction that will do the deduction (or the caller's
    # rollback) also persists/reverts the reset.
    entitlement_service.apply_monthly_reset(locked_balance, limits.free_monthly)

    if locked_balance.has_unlimited:
        db.flush()
        return True

    if locked_balance.scan_credits < count:
        return False

    locked_balance.scan_credits = locked_balance.scan_credits - count
    # NOTE: do NOT commit here. The caller commits after successful
    # processing, or rolls back on failure to undo the deduction.
    db.flush()
    return True


def _record_screenshot_usage(db: Session, user_id: str, count: int = 1) -> None:
    """Record screenshot usage for rate limiting. Flushes but does not commit."""
    usage = ScreenshotUsage(user_id=user_id, screenshots_count=count)
    db.add(usage)
    db.flush()


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
    save_activity: bool = Form(
        default=True,
        description=(
            "Auto-save activity screenshots. Pass false for the ARISE v2 §7.3 "
            "edit-before-save flow (then POST /screenshot/save-activity)."
        ),
    ),
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
    # Non-monetary rate limiting (feature flag, daily cap, cooldown)
    limits = entitlement_service.effective_limits(db, current_user.id)
    _check_screenshot_rate_limit(db, current_user.id, screenshot_count=1, limits=limits)

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

    # Atomic credit reservation + processing + usage record. Everything runs
    # inside a single transaction so a failure rolls back the deduction.
    try:
        reserved = _reserve_scan_credits(db, current_user.id, count=1, limits=limits)
        if not reserved:
            # Abandon the transaction opened by _reserve_scan_credits (no
            # mutations persisted since we short-circuit before flush).
            db.rollback()
            raise HTTPException(
                status_code=402,  # Payment Required
                detail="Insufficient scan credits. Purchase a scan pack to continue.",
            )

        logger.info("Calling extract_workout_from_screenshot...")
        result = await extract_workout_from_screenshot(
            image_data=content,
            filename=file.filename or "screenshot.png",
            db=db,
            user_id=current_user.id
        )
        logger.info(f"Extraction complete, screenshot_type: {result.get('screenshot_type')}")
        _record_screenshot_usage(db, current_user.id, count=1)
        # Commit the deduction + usage record together.
        db.commit()
    except HTTPException:
        # Preserve explicit HTTP responses (e.g. 402 above).
        raise
    except anthropic.APITimeoutError as e:
        db.rollback()
        logger.error(f"Anthropic API timeout: {e}")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Screenshot extraction timed out. No credit was consumed — please try again.",
        )
    except ValueError as e:
        db.rollback()
        logger.error(f"ValueError during extraction: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )
    except Exception as e:
        db.rollback()
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

    # If caller provided a manual date override, make it authoritative for both
    # persistence and response payload (instead of the model-extracted date).
    parsed_override_date = None
    effective_session_date = result.get("session_date")
    if session_date:
        try:
            parsed_override_date = datetime.strptime(session_date, "%Y-%m-%d")
            effective_session_date = session_date
            result["session_date"] = session_date
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid session_date format. Use YYYY-MM-DD."
            )

    # Auto-save workout if requested (only for gym workouts with matched exercises)
    workout_id = None
    workout_saved = False
    if save_workout and screenshot_type == "gym_workout" and exercises:
        try:
            workout_id = await save_extracted_workout(
                db=db,
                user_id=current_user.id,
                extraction_result=result,
                session_date=parsed_override_date,
                include_warmups=include_warmups
            )
            workout_saved = True
        except Exception as e:
            # Log full error details for debugging
            logger.error(f"[SINGLE SAVE ERROR] Failed to save workout: {str(e)}")
            logger.error(f"[SINGLE SAVE ERROR] Traceback:\n{traceback.format_exc()}")
            # Don't fail the whole request - still return extraction data

    # Auto-save WHOOP activity data (also creates a WorkoutSession for
    # calendar). Skipped when the client opts into the §7.3 edit-before-save
    # flow (save_activity=false → user edits → POST /screenshot/save-activity).
    activity_id = None
    activity_saved = False
    if screenshot_type == "whoop_activity" and save_activity:
        try:
            activity_id, whoop_workout_id = await save_whoop_activity(
                db=db,
                user_id=current_user.id,
                extraction_result=result,
                activity_date=parsed_override_date
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
        session_date=effective_session_date,
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

    # Non-monetary rate limiting (feature flag, daily cap, cooldown)
    limits = entitlement_service.effective_limits(db, current_user.id)
    _check_screenshot_rate_limit(db, current_user.id, screenshot_count=len(files), limits=limits)

    if len(files) > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 10 screenshots per batch"
        )

    # Pre-validate file types and sizes so we don't charge for malformed
    # uploads that we know will fail. Any validation error aborts the batch
    # before we reserve credits.
    file_contents: List[Tuple[UploadFile, bytes]] = []
    for file in files:
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file type for {file.filename}: {file.content_type}"
            )
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File too large: {file.filename}"
            )
        file_contents.append((file, content))

    # Atomic batch credit reservation — deduct len(files) up front under a
    # row lock so two concurrent batches can't each observe capacity for
    # the same credits. Commit IMMEDIATELY so the FOR UPDATE lock + DB
    # connection are released before we start awaiting Anthropic for ~30s
    # per file (holding the lock would pin a DB connection per in-flight
    # batch and exhaust the pool under load).
    #
    # TRADE-OFF: if the worker crashes mid-loop (OOM kill, SIGKILL, etc.)
    # the user's credits will be spent with no workouts extracted. We
    # accept that over the DB pool exhaustion risk of the previous design.
    # Successful-but-partial batches are reconciled via a best-effort
    # refund in a separate short transaction below.
    try:
        reserved = _reserve_scan_credits(db, current_user.id, count=len(files), limits=limits)
        if not reserved:
            db.rollback()
            raise HTTPException(
                status_code=402,
                detail="Insufficient scan credits. Purchase a scan pack to continue.",
            )
        # Record usage + commit deduction in the same short transaction so
        # the FOR UPDATE lock is released before any external calls.
        _record_screenshot_usage(db, current_user.id, count=len(files))
        db.commit()
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise

    # Process each screenshot. Track how many failed so we can refund
    # (compensating transaction) without penalizing the user for our
    # extraction errors.
    extractions = []
    failed_count = 0
    first_error: Optional[Exception] = None
    first_error_filename: Optional[str] = None

    for file, content in file_contents:
        try:
            result = await extract_workout_from_screenshot(
                image_data=content,
                filename=file.filename or "screenshot.png",
                db=db,
                user_id=current_user.id
            )
            extractions.append(result)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Failed to process {file.filename}: {str(e)}"
            )
        except anthropic.APITimeoutError as e:
            failed_count += 1
            if first_error is None:
                first_error = e
                first_error_filename = file.filename
            logger.error(f"[BATCH] Anthropic timeout on {file.filename}: {e}")
        except Exception as e:
            failed_count += 1
            if first_error is None:
                first_error = e
                first_error_filename = file.filename
            logger.error(f"[BATCH] Extraction failed on {file.filename}: {e}")

    # If EVERY file failed, refund all credits and raise. Reservation was
    # already committed above, so we must issue a compensating refund in a
    # fresh transaction rather than rolling back.
    if not extractions:
        _refund_scan_credits_safe(SessionLocal, current_user.id, count=len(files))
        if isinstance(first_error, anthropic.APITimeoutError):
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=(
                    f"Screenshot extraction timed out for {first_error_filename}. "
                    "No credits were consumed — please try again."
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process {first_error_filename}: {first_error}",
        )

    if failed_count > 0:
        # Partial success: credits were already deducted + committed above.
        # Issue a best-effort refund for the failed count in a fresh
        # transaction so partial success still bills correctly.
        _refund_scan_credits_safe(SessionLocal, current_user.id, count=failed_count)

    # Merge all extractions
    merged = merge_extractions(extractions)

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

    # If caller provided a manual date override, make it authoritative for both
    # persistence and response payload (instead of merged model-extracted date).
    parsed_override_date = None
    effective_session_date = merged.get("session_date")
    if session_date:
        try:
            parsed_override_date = datetime.strptime(session_date, "%Y-%m-%d")
            effective_session_date = session_date
            merged["session_date"] = session_date
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid session_date format. Use YYYY-MM-DD."
            )

    # Auto-save workout if requested (only for gym workouts)
    workout_id = None
    workout_saved = False
    if save_workout and screenshot_type == "gym_workout" and exercises:
        try:
            workout_id = await save_extracted_workout(
                db=db,
                user_id=current_user.id,
                extraction_result=merged,
                session_date=parsed_override_date,
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
            activity_id, whoop_workout_id = await save_whoop_activity(
                db=db,
                user_id=current_user.id,
                extraction_result=merged,
                activity_date=parsed_override_date
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
        session_date=effective_session_date,
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


@router.post("/save-activity", response_model=ActivitySaveResponse)
async def save_activity(
    payload: ActivitySaveRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Save a (possibly user-edited) activity extraction (ARISE v2 §7.3).

    Second half of the manual-controls flow: the client processes an activity
    screenshot with save_activity=false, lets the user edit duration and
    avg/max HR, then posts the edited fields here. Creates the DailyActivity
    row and a WorkoutSession with hr_source="screenshot".
    """
    parsed_date = None
    if payload.session_date:
        try:
            parsed_date = datetime.strptime(payload.session_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid session_date format. Use YYYY-MM-DD.",
            )

    extraction_result = {
        "activity_type": payload.activity_type,
        "session_date": payload.session_date,
        "time_range": payload.time_range,
        "duration_minutes": payload.duration_minutes,
        "strain": payload.strain,
        "steps": payload.steps,
        "calories": payload.calories,
        "avg_hr": payload.avg_hr,
        "max_hr": payload.max_hr,
        "heart_rate_zones": [zone.model_dump() for zone in payload.heart_rate_zones],
    }

    try:
        activity_id, workout_id = await save_whoop_activity(
            db=db,
            user_id=current_user.id,
            extraction_result=extraction_result,
            activity_date=parsed_date,
        )
    except Exception as e:
        logger.error(f"[SAVE-ACTIVITY ERROR] {e}")
        logger.error(f"[SAVE-ACTIVITY ERROR] Traceback:\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save activity",
        )

    return ActivitySaveResponse(activity_id=activity_id, workout_id=workout_id)
