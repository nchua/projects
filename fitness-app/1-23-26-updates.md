# Updates 1/23/26

## Bug Fix: Screenshot Batch Processing 500 Error

### Issue
Server error 500 when logging a workout with two screenshots via batch endpoint.

### Root Cause Investigation
The batch screenshot processing had exception handlers that swallowed errors without logging full details. Exceptions during `save_extracted_workout()` were caught but only logged a generic message without the traceback.

### Changes Made

#### `backend/app/api/screenshot.py`
- Added `import traceback` for full error tracebacks
- Updated all 4 exception handlers (single save, batch save, single WHOOP, batch WHOOP) to log:
  - Full traceback via `traceback.format_exc()`
  - Detailed context (exercise count, exercise names, matched IDs)
  - Tagged errors with `[SINGLE SAVE ERROR]`, `[BATCH SAVE ERROR]`, `[WHOOP SAVE ERROR]`, `[BATCH WHOOP SAVE ERROR]` for easy log searching

#### `backend/app/services/screenshot_service.py`
- Added logging before/after each `db.flush()` and `db.commit()` in `save_extracted_workout()`
- Added logging for:
  - Workout session creation
  - Each exercise being processed (with name and ID)
  - Skipped exercises (unmatched or not found in DB)
  - PR detection for each exercise
  - Both commit operations (mid-save and final)
- Tags all logs with `[SAVE]` prefix for easy filtering

### How to Debug
After deploying, if the error occurs again:
1. Go to Railway dashboard → Deployments → Logs
2. Search for `[BATCH SAVE ERROR]` or `[SAVE]` tags
3. The traceback will show the exact line and exception type

### Verification
1. Deploy to Railway
2. Test batch upload with 2 screenshots
3. Check Railway logs for detailed output
4. Confirm workout saves correctly or returns meaningful error with full traceback
