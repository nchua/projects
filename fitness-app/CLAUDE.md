# CLAUDE.md - Fitness App

Project instructions for Claude Code when working with this codebase.

## Project Overview

Solo Leveling-inspired fitness tracking app with iOS frontend and Python/FastAPI backend deployed on Railway.

## Architecture

```
fitness-app/
├── backend/           # FastAPI backend (Python)
│   ├── app/
│   │   ├── api/       # API endpoints (auth, workouts, exercises, etc.)
│   │   ├── core/      # Security, config
│   │   ├── models/    # SQLAlchemy models
│   │   └── schemas/   # Pydantic schemas
│   ├── alembic/       # Database migrations
│   └── main.py        # Entry point
├── ios/               # iOS app (Swift/SwiftUI)
│   └── FitnessApp/
│       ├── Views/     # SwiftUI views
│       ├── Services/  # APIClient, AuthManager
│       └── Models/    # Data models
└── *.js               # Test scripts
```

## Common Commands

### Backend
```bash
cd backend
source venv/bin/activate
python main.py                    # Run locally
alembic upgrade head              # Apply migrations
alembic revision --autogenerate -m "description"  # Create migration
```

### iOS
```bash
cd ios
xcodegen generate                 # Regenerate Xcode project
open FitnessApp.xcodeproj         # Open in Xcode
```

### Testing
```bash
node test-auth.js                 # Test authentication
node test-workouts.js             # Test workout endpoints
node test-exercises.js            # Test exercise endpoints
```

## Deployment

- **Backend**: Railway (https://backend-production-e316.up.railway.app)
- **Git**: https://github.com/nchua/projects.git
- **Branch**: `main` (Railway watches this branch for auto-deploy)

```bash
git push origin main              # Deploy to Railway
```

## Environment Variables

### Backend (Railway)
- `DATABASE_URL` - PostgreSQL connection string
- `JWT_SECRET_KEY` - JWT signing key
- `ANTHROPIC_API_KEY` - For screenshot processing

### Local Scripts
- `API_BASE_URL` - Backend URL (default: localhost:8000)
- `SEED_USER_EMAIL` - Email for seed scripts
- `SEED_USER_PASSWORD` - Password for seed scripts

---

## Security Guidelines

### NEVER Commit Credentials

**Incident (Jan 2026)**: Hardcoded email/password in `seed_user_data.py` was pushed to GitHub and detected by GitGuardian.

**Resolution required**:
1. Remove credentials from source files
2. Scrub from git history with `git filter-branch`
3. Force push to overwrite remote history
4. Rotate any exposed passwords

### Rules for Claude Code

1. **NEVER hardcode credentials** in any file that will be committed
   - No real emails, passwords, API keys, or tokens
   - Use environment variables: `os.environ.get("VAR_NAME")`
   - Use placeholder values: `test@example.com`, `TestPass123!`

2. **Check before committing** seed scripts, test files, or config files for:
   - Real email addresses (especially `@gmail.com`)
   - Passwords that look real (not obvious test passwords)
   - API keys or tokens

3. **Use .env files** for local development (already in .gitignore)

4. **Sensitive files to watch**:
   - `backend/seed_user_data.py` - uses env vars
   - `import_workouts.py` - uses env vars
   - Any new seed/test scripts

### If Credentials Are Accidentally Committed

```bash
# 1. Create backup branch
git branch backup-$(date +%Y%m%d)

# 2. Fix the file (replace with env vars)
# 3. Commit the fix

# 4. Rewrite history to scrub credentials
FILTER_BRANCH_SQUELCH_WARNING=1 git filter-branch -f --tree-filter '
if [ -f path/to/file.py ]; then
  sed -i "" "s/real@email.com/test@example.com/g" path/to/file.py
fi
' --tag-name-filter cat -- --all

# 5. Force push
git push origin main --force

# 6. Clean up
rm -rf .git/refs/original
git reflog expire --expire=now --all
git gc --prune=now --aggressive

# 7. CHANGE THE EXPOSED PASSWORD if used elsewhere!
```

---

## Workout Data Display Guidelines

### IMPORTANT: When Changing Workout Data Sources

When modifying how workout data is fetched, stored, or structured, you MUST update ALL places that display workout information. The app displays workouts in multiple locations:

**Backend data flow:**
1. `backend/app/schemas/workout.py` - `WorkoutSummary` and `WorkoutResponse` schemas
2. `backend/app/api/workouts.py` - `/workouts` list endpoint and `/workouts/{id}` detail endpoint
3. `backend/app/services/screenshot_service.py` - Screenshot extraction and processing

**iOS display locations:**
1. `ios/.../Views/Home/HomeView.swift` - `LastQuestCard` shows recent workout summary
2. `ios/.../Views/History/HistoryView.swift` - `CompletedQuestRow` and `QuestDetailView`
3. `ios/.../Services/APITypes.swift` - `WorkoutSummaryResponse`, `WorkoutResponse`, `ScreenshotProcessResponse`

### Checklist When Adding New Workout Fields

- [ ] Add field to backend Pydantic schema (`schemas/workout.py`)
- [ ] Update backend API endpoint to populate the field (`api/workouts.py`)
- [ ] Add field to iOS Decodable struct (`APITypes.swift`)
- [ ] Update iOS views that display workout data (`HomeView.swift`, `HistoryView.swift`)
- [ ] If screenshot-related, update `screenshot_service.py` and `schemas/screenshot.py`

---

## Problem-Solving Guidelines

### When Automatic Fixes Fail, Consider Manual User Controls

**Lesson Learned (Jan 2026)**: When debugging timezone/date issues with workout dates showing on the wrong calendar day, multiple attempts to fix the automatic date handling (ISO8601DateFormatter, timezone conversions, UTC vs local time) did not resolve the issue quickly.

**Better Approach**: Instead of continuing to debug complex automatic behavior, add a **manual override option** that gives users direct control.

**Example - Date Selection for Screenshots**:
- **Problem**: Workouts uploaded via screenshot showed on wrong calendar date due to server UTC vs user local time
- **Attempted fixes**: Multiple timezone conversion fixes in iOS and backend - none worked reliably
- **Solution**: Added a date picker screen before screenshot processing, letting users explicitly select the workout date

**When to consider manual controls**:
1. **Timezone/date issues** - Let users pick the date instead of auto-detecting
2. **Data extraction errors** - Let users edit/correct extracted data
3. **Ambiguous inputs** - Ask users to clarify rather than guessing
4. **Environment-dependent behavior** - Server vs client differences

**Benefits of manual controls**:
- Users get correct results immediately
- Avoids complex debugging of edge cases
- More transparent behavior
- Often simpler to implement than fixing root cause

**Implementation pattern**:
```
Before: Auto-process → Save with auto-detected values → User sees wrong result
After:  Show preview → User adjusts values → Process with user's values → Correct result
```

---

## Recent Changes Summary (Jan 2026)

### Bug Fix: Exercise Names in Completed Quest Card

**Problem**: `LastQuestCard` in `HomeView.swift` displayed "Exercise 1", "Exercise 2" instead of actual names.

**Root Cause**: `WorkoutSummaryResponse` only had `exerciseCount` (integer), not actual names. The UI used loop index: `Text("Exercise \(index + 1)")`.

**Files Modified**:
- `backend/app/schemas/workout.py` - Added `exercise_names: List[str]` to `WorkoutSummary`
- `backend/app/api/workouts.py` - Updated `/workouts` endpoint to include exercise names
- `ios/.../APITypes.swift` - Added `exerciseNames: [String]?` to `WorkoutSummaryResponse`
- `ios/.../HomeView.swift` - `LastQuestCard` now uses `exerciseNamesToShow` computed property

### Feature: WHOOP Screenshot Support

**Problem**: Screenshot analyzer only recognized gym workout screenshots, not WHOOP activity screenshots.

**Solution**: Updated Claude Vision prompt to detect screenshot type and extract appropriate data.

**Files Modified**:
- `backend/app/services/screenshot_service.py`:
  - Updated `EXTRACTION_PROMPT` to detect `gym_workout` vs `whoop_activity`
  - Added WHOOP-specific extraction (strain, HR zones, calories, steps, activity type)
  - Modified `extract_workout_from_screenshot()` to return appropriate data per type

- `backend/app/schemas/screenshot.py`:
  - Added `HeartRateZone` model
  - Added WHOOP fields to `ScreenshotProcessResponse` and `ScreenshotBatchResponse`
  - Added `screenshot_type` field

- `backend/app/api/screenshot.py`:
  - Updated both endpoints to include WHOOP data in response
  - Only auto-saves workouts for gym screenshots (not WHOOP activities)

- `ios/.../APITypes.swift`:
  - Added `HeartRateZone` struct
  - Added WHOOP fields and `isWhoopActivity` computed property to response structs

- `ios/.../ScreenshotProcessingViewModel.swift`:
  - Added WHOOP detection properties (`isWhoopActivity`, `activityType`, `whoopStrain`, etc.)
  - Updated `convertToLoggedExercises()` to return empty for WHOOP activities

**WHOOP Data Extracted**:
- `activity_type` (e.g., "TENNIS", "RUNNING")
- `strain` score
- `steps`, `calories`, `avg_hr`, `max_hr`
- `heart_rate_zones` with BPM ranges, percentages, durations
- `time_range` and `source` (e.g., "VIA APPLE WATCH")
