# Apple HealthKit Integration

## Overview

This document summarizes the HealthKit integration added to the fitness app, connecting it to Apple Health to sync steps, calories, and activity data.

## Backend (Railway) - Complete

Added `/activity` API endpoints to the existing FastAPI backend:

| Endpoint | Purpose |
|----------|---------|
| `POST /activity/` | Sync single day's activity (upsert) |
| `POST /activity/bulk` | Bulk sync multiple days |
| `GET /activity/` | Get activity history with date filters |
| `GET /activity/today` | Get today's activity |
| `GET /activity/last-sync` | Get last synced date for a source |

### Files Created
- `backend/app/schemas/activity.py` - Pydantic request/response models
- `backend/app/models/activity.py` - SQLAlchemy DailyActivity model
- `backend/app/api/activity.py` - FastAPI router with endpoints

### Database Schema
New `daily_activity` table with unique constraint on `(user_id, date, source)` for upsert behavior.

### Deployment
Live at `https://backend-production-e316.up.railway.app`

---

## iOS App - Complete

Integrated HealthKit into the existing SwiftUI app.

### New Files
- `ios/FitnessApp/Services/HealthKitManager.swift` - Queries HealthKit for steps, calories, exercise minutes, stand hours
- `ios/FitnessApp/FitnessApp.entitlements` - HealthKit capability entitlements

### Modified Files
- `APIClient.swift` - Added `syncActivity()`, `syncActivityBulk()`, `getActivityHistory()`, etc.
- `APITypes.swift` - Added `ActivityCreate`, `ActivityResponse`, `ActivitySource` enum
- `HomeViewModel.swift` - Added `loadHealthKitData()`, `syncHealthKit()`, `requestHealthKitAccess()`, weekly stats properties
- `HomeView.swift` - Added `ActivityRingsCard` and `HealthKitConnectCard` components with 1D/7D toggle
- `project.yml` - Added HealthKit capability, entitlements, Info.plist permissions

### UI Components
Home screen now shows:
1. **"Connect Apple Health" card** - Shown if HealthKit not yet authorized
2. **Activity Rings card** - Shows steps, calories, exercise minutes, stand hours with progress rings
   - **1D button** - Today's stats with circular progress indicators
   - **7D button** - Weekly totals (steps, calories, exercise, avg steps/day)

---

## How It Works

1. User opens app -> HomeView loads
2. If HealthKit authorized -> fetches today's stats and weekly stats, displays them
3. Stats sync to backend via `POST /activity/`
4. Manual refresh button triggers full sync of last 7 days
5. Backend uses upsert logic (same date+source updates existing record)

### Data Flow
```
Apple Health -> HealthKitManager -> HomeViewModel -> APIClient -> Railway Backend
     ^                                                              |
   (read)                                                    daily_activity table
```

---

## Session Changes (Jan 3, 2026)

### HealthKit Permission Issues Fixed

1. **Removed restricted entitlements** that blocked personal team provisioning:
   - Removed `com.apple.developer.healthkit.access` (Clinical Health Records - requires Apple approval)
   - Removed `com.apple.developer.healthkit.background-delivery` (restricted for personal teams)
   - Kept only `com.apple.developer.healthkit: true` (basic HealthKit)

2. **Updated files:**
   - `ios/FitnessApp/FitnessApp.entitlements` - Simplified to basic HealthKit entitlement only
   - `ios/project.yml` - Removed restricted entitlement properties

### Weekly Stats Feature Added

1. **HealthKitManager.swift**:
   - Added `@Published` properties: `weeklySteps`, `weeklyCalories`, `weeklyExerciseMinutes`, `weeklyAvgSteps`
   - Added `fetchWeeklyStats()` function that queries last 7 days of data
   - `fetchTodayStats()` now also calls `fetchWeeklyStats()`

2. **HomeViewModel.swift**:
   - Added weekly stat properties to pass to view
   - `loadHealthKitData()` now updates both today and weekly stats

3. **HomeView.swift - ActivityRingsCard**:
   - Added 1D/7D toggle button to switch between today and weekly view
   - Today view: Steps, Calories, Exercise, Stand hours with progress rings
   - Weekly view: Total steps, Total calories, Avg steps/day, Total exercise minutes
   - Added new `WeeklyStatItem` component for weekly stats display

---

## Build & Test on Device

```bash
cd ios
xcodegen generate  # Regenerate if needed
open FitnessApp.xcodeproj
```

Build and run on a **physical iPhone** (HealthKit unavailable in Simulator).

### Apple Developer Portal
May need to enable HealthKit capability for your App ID if not already done:
- Go to developer.apple.com -> Certificates, Identifiers & Profiles
- Select your App ID -> Enable HealthKit

---

## Future Enhancements

- [ ] Background sync using `BGTaskScheduler`
- [ ] Write workouts back to HealthKit (currently read-only)
- [ ] Sync bodyweight from HealthKit
- [ ] Historical data import on first authorization
- [ ] Weekly/monthly activity trends in analytics

---

## Key Files Reference

| Component | Location |
|-----------|----------|
| Backend activity API | `backend/app/api/activity.py` |
| Backend activity model | `backend/app/models/activity.py` |
| Backend activity schemas | `backend/app/schemas/activity.py` |
| iOS HealthKit manager | `ios/FitnessApp/Services/HealthKitManager.swift` |
| iOS API client | `ios/FitnessApp/Services/APIClient.swift` |
| iOS API types | `ios/FitnessApp/Services/APITypes.swift` |
| iOS HomeView | `ios/FitnessApp/Views/Home/HomeView.swift` |
| iOS HomeViewModel | `ios/FitnessApp/Views/Home/HomeViewModel.swift` |
| Project config | `ios/project.yml` |
| Entitlements | `ios/FitnessApp/FitnessApp.entitlements` |

---

## API Examples

### Sync Today's Activity
```bash
curl -X POST "https://backend-production-e316.up.railway.app/activity/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "date": "2026-01-03",
    "source": "apple_fitness",
    "steps": 8542,
    "active_calories": 425,
    "exercise_minutes": 32,
    "stand_hours": 10
  }'
```

### Get Activity History
```bash
curl "https://backend-production-e316.up.railway.app/activity/?limit=7" \
  -H "Authorization: Bearer $TOKEN"
```

### Check Last Sync
```bash
curl "https://backend-production-e316.up.railway.app/activity/last-sync?source=apple_fitness" \
  -H "Authorization: Bearer $TOKEN"
```
