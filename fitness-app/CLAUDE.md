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

---

## iOS Development Guidelines

### IMPORTANT: Rebuild After iOS Changes

After modifying any iOS Swift files, the user must rebuild the app in Xcode for changes to take effect on their device.

**After committing iOS changes, always remind the user:**
> "iOS changes committed. To see them on your device, rebuild in Xcode (Cmd+R) or run:
> ```bash
> cd ios && xcodegen generate && open FitnessApp.xcodeproj
> ```
> Then build and run (Cmd+R)."

**If adding new Swift files:**
1. Run `xcodegen generate` to update the Xcode project
2. Open in Xcode and build (Cmd+R)

**Quick rebuild command:**
```bash
cd /Users/nickchua/Desktop/AI/Fitness\ App/fitness-app/fitness-app/ios && xcodegen generate && open FitnessApp.xcodeproj
```

---

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

## Git Safety Guidelines

### Before Destructive Operations

**ALWAYS check the current branch before:**
- Deleting files or large sections of code
- Resetting or reverting commits
- Force pushing
- Major refactors that touch many files

```bash
git branch                    # Check current branch
git status                    # Check for uncommitted changes
git log --oneline -5          # Verify recent commit history
```

### Recovering Lost Work

If code is missing or needs recovery:
1. **Check GitHub first** - The remote repo may have commits not in local
   ```bash
   git fetch origin
   git log origin/main --oneline -10    # See remote commits
   git diff main origin/main            # Compare local vs remote
   ```
2. **Pull from remote** if behind:
   ```bash
   git pull origin main
   ```
3. **Check reflog** for recently deleted local commits:
   ```bash
   git reflog                           # Shows all recent HEAD positions
   git checkout <commit-hash>           # Recover specific commit
   ```

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

## Date Parsing: Backend ↔ iOS Format Compatibility

### CRITICAL: iOS parseISO8601Date() Supported Formats

The iOS date parser in `Extensions.swift` handles these formats:

| Format | Example | Source |
|--------|---------|--------|
| ISO8601 with fractional seconds | `2025-12-12T12:00:00.123Z` | Rare |
| ISO8601 with timezone | `2025-12-12T12:00:00Z` | Standard API responses |
| ISO8601 WITHOUT timezone | `2025-12-12T12:00:00` | Python `datetime.isoformat()` |
| Date only | `2025-12-12` | Python `date.isoformat()` |

### Bug Pattern: Charts Not Rendering (Jan 2026)

**Symptom**: Power chart (e1RM) showed Y-axis grid but NO line or data points. Debug showed valid data (4 points, dates spanning Dec-Jan).

**Root Cause**: Backend returned dates as `2025-12-12T12:00:00` (ISO8601 without timezone). The iOS parser only handled formats WITH timezone (`Z` suffix) or date-only. The format without timezone returned `nil`, causing all data points to collapse to the same X coordinate (fallback `Date()`).

**Fix**: Added handler for ISO8601 without timezone in `parseISO8601Date()`:
```swift
// Try ISO8601 WITHOUT timezone: "2025-12-12T12:00:00"
let noTimezoneFormatter = DateFormatter()
noTimezoneFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
noTimezoneFormatter.timeZone = TimeZone(identifier: "UTC")
if let date = noTimezoneFormatter.date(from: self) {
    return date
}
```

### Prevention Checklist

When backend returns date strings to iOS:
- [ ] Check what format Python is returning (`datetime.isoformat()` vs `date.isoformat()`)
- [ ] Verify iOS `parseISO8601Date()` handles that format
- [ ] If chart/data doesn't render, add debug output to check if dates parse to `nil`

**Debug pattern for date issues**:
```swift
// Add temporarily to chart view
Text("DEBUG: \(dataPoints.count) pts, first: \(dataPoints.first?.date ?? "none")")
    .background(Color.yellow)
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

### Feature: Expanded Strength Standards (Jan 2026)

**Problem**: Stats page only showed percentile rankings for Big Three exercises (squat, bench, deadlift). Additional skills like Barbell Curl showed rank badge but no percentile.

**Solution**: Added strength standards (bodyweight multipliers) for 17 additional exercises.

**Files Modified**:
- `backend/app/api/analytics.py`:
  - Expanded `STRENGTH_STANDARDS` dict with new exercises
  - Updated `CANONICAL_EXERCISE_KEYWORDS` for exercise name matching

**Exercises Now Supported**:
| Category | Exercises |
|----------|-----------|
| Big Three | squat, bench, deadlift |
| Pressing | overhead press, incline bench, dip |
| Pulling | row, pullup/chinup, lat pulldown |
| Arms | curl, tricep extension |
| Legs | leg press, romanian deadlift, hip thrust, leg curl, leg extension, calf raise |
| Shoulders | lateral raise, face pull |
| Chest | fly/pec deck |

**Keyword Matching Examples**:
- "Barbell Curl" / "Bicep Curl" / "Hammer Curl" → `curl`
- "Lat Pulldown" / "Pulldown" → `lat_pulldown`
- "RDL" / "Romanian Deadlift" / "Stiff Leg Deadlift" → `romanian_deadlift`
- "Skull Crusher" / "Tricep Pushdown" → `tricep_extension`
- "Pull Up" / "Chin Up" → `pullup`

**iOS Changes** (`StatsView.swift`):
- `AdditionalExerciseCard` now shows trend percentage and rank badge (matches Big Three cards)
- Rank badge only displays when real percentile data exists
- Trend indicator hidden for "insufficient_data" (requires 4+ weeks of data)

### Bug Fix: Black Screen After PR Celebration (Jan 2026)

**Problem**: After PR celebration from screenshot-logged workout, app shows black screen requiring restart.

**Root Cause**:
1. `fullScreenCover` for PR celebration had no fallback when `prQueue` was empty
2. Auto-dismiss timer in `PRCelebrationView` could fire after manual dismissal, calling `onDismiss()` twice
3. Race condition between dismiss animation and state reset

**Files Modified**:
- `ios/.../Views/Log/LogView.swift` - Added EmptyView fallback with auto-dismiss in PR celebration fullScreenCover
- `ios/.../Components/PRCelebrationView.swift` - Added `isDismissed` guard to prevent double dismissal

**Fix Pattern**: When using `fullScreenCover(isPresented:)` with conditional content, ALWAYS include an else branch that either shows content or immediately dismisses to prevent black screens.

### Build Error: Duplicate Swift Struct Names (Jan 2026)

**Problem**: iOS build failed with "Invalid redeclaration of 'EdgeFlowQuestRow'"

**Root Cause**: Two different structs with the same name existed in different files:
- `DailyQuestsCard.swift:36` - `EdgeFlowQuestRow` taking `QuestResponse`
- `QuestsView.swift:467` - `EdgeFlowQuestRow` taking `WorkoutSummaryResponse`

Swift doesn't allow duplicate type names at the same scope level, even across different files.

**Fix**: Renamed the workout-focused struct to `EdgeFlowWorkoutRow` to reflect its actual purpose.

**Prevention Rules**:
1. **Use descriptive, unique struct names** - Include the data type in the name (e.g., `QuestRow` vs `WorkoutRow`)
2. **Before creating new View structs**, search the codebase: `grep -r "struct YourStructName" ios/`
3. **When copying/adapting UI components**, always rename them to avoid collisions
4. **Naming convention**: `{DesignSystem}{DataType}{ComponentType}` (e.g., `EdgeFlowWorkoutRow`, `EdgeFlowQuestCard`)

---

## SwiftUI fullScreenCover State Management (CRITICAL)

### Problem: Black Screen from Stale @State in fullScreenCover

**Symptom**: After dismissing a fullScreenCover, the app shows an indefinite black screen requiring restart.

**Root Cause**: SwiftUI view reuse with stale `@State` variables. When using `fullScreenCover(isPresented:)` with:
1. Conditional content (`if index < array.count`)
2. Views that have internal `@State` (e.g., `@State private var isDismissed = false`)

SwiftUI may **reuse** the existing view instance instead of creating a new one when the condition changes but `isPresented` stays true. This causes:
- `@State` variables retain their old values (e.g., `isDismissed = true` from previous dismissal)
- The view appears but doesn't function correctly
- Dismiss callbacks never fire, leaving the cover stuck

### The Pattern That Causes Black Screens

```swift
// DANGEROUS: No .id() modifier when iterating through items
.fullScreenCover(isPresented: $showCelebration) {
    if currentIndex < items.count {
        CelebrationView(item: items[currentIndex], onDismiss: { handleDismiss() })
        // ❌ When currentIndex changes, SwiftUI may reuse this view with stale @State
    } else {
        Color.clear.onAppear { showCelebration = false }  // ❌ May not dismiss properly
    }
}
```

### The Fix: Force View Recreation with .id()

```swift
// SAFE: .id() forces new view instance when index changes
.fullScreenCover(isPresented: $showCelebration) {
    if currentIndex < items.count {
        CelebrationView(item: items[currentIndex], onDismiss: { handleDismiss() })
            .id(currentIndex)  // ✅ Forces fresh view with reset @State
    } else {
        Color.clear
            .onAppear {
                // ✅ Full cleanup in fallback
                items = []
                currentIndex = 0
                showCelebration = false
            }
    }
}
```

### Rules for fullScreenCover Usage

1. **Always use `.id()` when iterating through items** in a fullScreenCover
   - Add `.id(currentIndex)` or `.id(item.id)` to force view recreation

2. **Prepare next state BEFORE dismissing**
   - Set up the next view's data before setting `isPresented = false`
   - Prevents intermediate states where cover shows empty content

3. **Fallback branches must clean up completely**
   - Don't just set `isPresented = false`
   - Reset all related state variables
   - Transition to a valid app state (e.g., return to idle)

4. **Guard against double dismissal in views with auto-dismiss**
   - If a view has a timer that calls `onDismiss()`, add a guard:
   ```swift
   @State private var isDismissed = false

   private func dismissWithAnimation() {
       guard !isDismissed else { return }  // Prevent double-fire
       isDismissed = true
       onDismiss()
   }
   ```

### Lint Script

Run `ios/scripts/lint-fullscreen-cover.sh` to detect potential issues:
```bash
./ios/scripts/lint-fullscreen-cover.sh
```

This checks for:
- `fullScreenCover(isPresented:` with conditional content but no `.id()` modifier
- Views with `@State` that might become stale

### Files Most at Risk

- `LogView.swift` - Multiple celebration fullScreenCovers (PR, rank-up, XP)
- Any view that cycles through multiple items in a fullScreenCover
- Views with auto-dismiss timers

---

## SwiftUI .onChange Infinite Loop Prevention (CRITICAL)

### Problem: Re-triggering .onChange with Same Data

**Symptom**: App freezes or shows black screen after completing a multi-step celebration flow.

**Root Cause**: When using `.onChange(of:)` to intercept and redirect state, setting the observed value back to a previously-seen value re-triggers the handler, causing infinite loops.

### The Pattern That Causes Loops

```swift
// LogView.swift - Celebration flow
.onChange(of: viewModel.xpRewardResponse?.id) { oldValue, newValue in
    guard let response = viewModel.xpRewardResponse else { return }

    // BUG: After PR celebration completes, we set xpRewardResponse = pendingResponse
    // This triggers onChange again, which sees prsAchieved is NOT empty
    // and restarts the PR celebration flow!
    if !response.prsAchieved.isEmpty {
        prQueue = response.prsAchieved  // Sets up PR flow
        pendingXPResponse = response     // Saves response for later
        viewModel.xpRewardResponse = nil // Clears to show PRs first
        showPRCelebration = true
        return
    }
    // ...
}

// Later, in handlePRDismiss:
viewModel.xpRewardResponse = pendingXPResponse  // RE-TRIGGERS onChange!
```

### The Fix: Track Processed Responses

```swift
.onChange(of: viewModel.xpRewardResponse?.id) { oldValue, newValue in
    guard let response = viewModel.xpRewardResponse else { return }

    // CRITICAL: Skip if this response was already processed
    if let pending = pendingXPResponse, pending.id == response.id {
        pendingXPResponse = nil  // Clear the flag
        return  // Let XP view show directly without re-processing
    }

    // Now safe to check for PRs/rank-up
    // ...
}
```

### Rules for .onChange with State Redirection

1. **Track processed items** - Use a flag or ID comparison to detect re-entry
2. **Clear the tracking flag** in the skip branch to allow future legitimate triggers
3. **Never assume .onChange won't re-trigger** - Always guard against loops
4. **Test the full flow** - Especially when chaining multiple celebrations/states
