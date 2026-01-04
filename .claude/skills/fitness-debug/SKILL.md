---
name: fitness-debug
description: Debug fitness app issues across iOS, backend, and screenshot processing. Use when troubleshooting errors, API failures, data sync issues, or investigating bugs in workouts, exercises, or authentication.
---

# Fitness App Debugging

## Quick Diagnosis

### 1. Identify the Layer
- **iOS crash/UI issue** → Check Swift views and view models
- **API error (4xx/5xx)** → Check backend logs and endpoint code
- **Data not showing** → Check API response, iOS decoding, database
- **Screenshot processing** → Check Claude Vision service and response parsing

## Key Files by Component

### Backend (FastAPI)
| Issue Type | Files to Check |
|------------|----------------|
| Auth failures | `backend/app/api/auth.py`, `backend/app/core/security.py` |
| Workout CRUD | `backend/app/api/workouts.py`, `backend/app/schemas/workout.py` |
| Exercise lookup | `backend/app/api/exercises.py`, `backend/app/models/exercise.py` |
| PR calculations | `backend/app/api/progress.py`, `backend/app/core/e1rm.py` |
| Screenshot extraction | `backend/app/services/screenshot_service.py` |
| Database issues | `backend/app/core/database.py`, `backend/alembic/versions/` |

### iOS (SwiftUI)
| Issue Type | Files to Check |
|------------|----------------|
| API calls failing | `ios/FitnessApp/Services/APIClient.swift`, `ios/FitnessApp/Services/APITypes.swift` |
| Auth/login issues | `ios/FitnessApp/Services/AuthManager.swift` |
| Home screen | `ios/FitnessApp/Views/Home/HomeView.swift`, `HomeViewModel.swift` |
| Workout history | `ios/FitnessApp/Views/History/HistoryView.swift`, `HistoryViewModel.swift` |
| Screenshot upload | `ios/FitnessApp/Views/Log/ScreenshotProcessingViewModel.swift` |
| Data decoding | `ios/FitnessApp/Services/APITypes.swift` (check Decodable structs) |

## Common Debugging Commands

### Test Backend API
```bash
# Health check
curl https://backend-production-e316.up.railway.app/health

# Test auth
node fitness-app/test-auth.js

# Test workouts
node fitness-app/test-workouts.js

# Test exercises
node fitness-app/test-exercises.js

# Manual API call with auth
curl -H "Authorization: Bearer $TOKEN" \
  https://backend-production-e316.up.railway.app/api/workouts
```

### Check Railway Logs
```bash
railway logs --latest
```

### Run Backend Locally
```bash
cd fitness-app/backend
source venv/bin/activate
python main.py
# Then test against localhost:8000
```

## Common Issues & Solutions

### 1. "Unauthorized" / 401 Errors
**Symptoms**: API calls return 401
**Check**:
- Is token expired? (30-day expiry by default)
- Is `Authorization: Bearer <token>` header correct?
- Check `backend/app/core/security.py` for JWT validation

### 2. Workout Data Missing/Wrong
**Symptoms**: Workouts show wrong date, missing exercises, or wrong names
**Check**:
- Backend response: Does `/api/workouts` return correct data?
- iOS decoding: Does `APITypes.swift` match backend schema?
- Timezone issues: Check date handling in both layers

### 3. Screenshot Processing Fails
**Symptoms**: Screenshot upload returns error or wrong data
**Check**:
- `ANTHROPIC_API_KEY` set in Railway environment
- Claude Vision prompt in `screenshot_service.py`
- Response parsing in `ScreenshotProcessingViewModel.swift`
- Image format (JPEG/PNG) and size limits

### 4. Exercise Names Not Matching
**Symptoms**: "Unknown exercise" or exercises not linking to PRs
**Check**:
- Canonical name mapping in `backend/app/models/exercise.py`
- Exercise aliases in database
- Case sensitivity in lookups

### 5. PRs Not Calculating
**Symptoms**: Personal records not updating after workouts
**Check**:
- e1RM calculation in `backend/app/core/e1rm.py`
- PR detection logic in `backend/app/api/progress.py`
- Set data has valid weight/reps

### 6. iOS Build Errors
**Symptoms**: Xcode build fails
**Check**:
- Run `xcodegen generate` to regenerate project
- Check Swift syntax errors in modified files
- Ensure all new files added to project

## Debugging Workflow

1. **Reproduce** - Get exact error message or behavior
2. **Isolate layer** - Is it iOS, API, or database?
3. **Check logs** - Railway logs for backend, Xcode console for iOS
4. **Test API directly** - Use curl or test scripts to bypass iOS
5. **Compare schemas** - Ensure backend response matches iOS Decodable
6. **Check recent changes** - What was modified since it last worked?

## Data Flow Reference

```
iOS App
  ↓ APIClient.swift (HTTP requests)
  ↓ Authorization header with JWT
FastAPI Backend
  ↓ Route handlers (api/*.py)
  ↓ Pydantic validation (schemas/*.py)
  ↓ SQLAlchemy ORM (models/*.py)
PostgreSQL (Railway)
```

## Environment Variables to Verify

### Railway Backend
- `DATABASE_URL` - PostgreSQL connection
- `SECRET_KEY` - JWT signing (must match between deploys)
- `ANTHROPIC_API_KEY` - For screenshot processing

### Local Testing
- `API_BASE_URL` - Target backend URL
- `SEED_USER_EMAIL` / `SEED_USER_PASSWORD` - Test credentials
