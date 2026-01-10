# Fitness App - Quick Start Guide

A Solo Leveling-inspired fitness tracking app with iOS frontend and Python/FastAPI backend.

---

## TL;DR

- **iOS App**: SwiftUI with gamification (XP, ranks, quests, achievements)
- **Backend**: FastAPI deployed on Railway
- **Database**: PostgreSQL (Railway) / SQLite (local)
- **Key Feature**: Screenshot processing using Claude Vision to extract workout data

---

## Architecture

```
Fitness App/fitness-app/fitness-app/
├── backend/              # FastAPI (Python)
│   ├── app/
│   │   ├── api/          # REST endpoints
│   │   ├── models/       # SQLAlchemy models
│   │   ├── schemas/      # Pydantic schemas
│   │   └── services/     # Business logic (screenshot processing, XP, PRs)
│   └── main.py
└── ios/FitnessApp/       # SwiftUI (Swift)
    ├── Views/            # UI screens
    ├── Services/         # APIClient, AuthManager
    ├── Models/           # Data models
    └── Components/       # Reusable UI (XPBar, StatCard, etc.)
```

---

## Key Commands

### Backend

```bash
cd "/Users/nickchua/Desktop/AI/Fitness App/fitness-app/fitness-app/backend"
source venv/bin/activate
python main.py                        # Run locally on port 8000
```

### iOS

```bash
cd "/Users/nickchua/Desktop/AI/Fitness App/fitness-app/fitness-app/ios"
xcodegen generate                     # Regenerate Xcode project
open FitnessApp.xcodeproj             # Open in Xcode
```

### Deploy to Railway

```bash
cd "/Users/nickchua/Desktop/AI/Fitness App/fitness-app/fitness-app"
git add -A && git commit -m "message" && git push origin main
# Railway auto-deploys from main branch
```

---

## Deployment Info

- **Backend URL**: https://backend-production-e316.up.railway.app
- **Git Repo**: https://github.com/nchua/projects.git
- **Branch**: `main` (Railway watches for auto-deploy)

---

## Environment Variables (Railway)

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection string |
| `JWT_SECRET_KEY` | JWT signing key |
| `ANTHROPIC_API_KEY` | Claude Vision for screenshot processing |

---

## Core Features (Implemented)

### Working
- User authentication (JWT)
- Workout logging (manual + screenshot upload)
- XP/Level/Rank system (E-rank to S-rank)
- Personal Record (PR) detection
- Progress charts with clickable data points
- Bodyweight tracking
- Daily quests
- 18 achievements
- WHOOP activity screenshot support
- Session expiry auto-redirect to login

### Screenshot Processing
- Upload gym app screenshots
- Claude Vision extracts exercises, sets, reps, weight
- Also supports WHOOP activity screenshots (strain, HR, etc.)

---

## Data Models

```
User
├── WorkoutSession (date, duration, session_rpe, notes)
│   └── WorkoutExercise
│       └── Set (weight, reps, rpe, rir, e1rm)
├── BodyweightEntry (weight, unit, date)
├── PersonalRecord (exercise, weight, reps, e1rm)
├── UserProgress (xp, level, rank, streak)
└── UserAchievement (achievement, unlocked_at)
```

---

## Gamification System

### XP Rewards
| Action | XP |
|--------|-----|
| Complete workout | 50 base |
| Volume bonus | 0.001 per lb |
| Big Three set | 5 per set |
| PR achieved | 100 |
| 7-day streak | 150 |

### Ranks (by Level)
- E-Rank: 1-10
- D-Rank: 11-25
- C-Rank: 26-45
- B-Rank: 46-70
- A-Rank: 71-90
- S-Rank: 91+

---

## Known Issues / Lessons Learned

1. **WHOOP Date Extraction**: Claude Vision doesn't always extract the date from WHOOP screenshots. Fallback uses EXIF date (when screenshot was taken, not when activity occurred). Consider adding a date picker as manual override.

2. **Security**: Never hardcode credentials. Use environment variables. A credential leak incident occurred in Jan 2026 - see `CLAUDE.md` for recovery steps.

3. **iOS JSON Decoding**: Don't use `.convertFromSnakeCase` - it breaks fields with numbers like `e1rm`. Use explicit `CodingKeys` instead.

4. **SwiftData Enums**: Use `WeightUnit.lb` not `.lb` in default values.

5. **Session Expiry**: `APIClient` has an `onSessionExpired` callback that triggers `AuthManager.logout()` automatically.

6. **Numeric TextField Deletion**: Don't use `TextField(value:format:.number)` for numeric inputs - users can't delete back to empty (stuck at 0). Use String-backed properties instead: `TextField(text: $weightText)` with computed `var weight: Double { Double(weightText) ?? 0 }`.

7. **Keyboard Dismissal Pattern**: Add tap-to-dismiss and Done button to all views with text input:
   ```swift
   .onTapGesture {
       UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
   }
   .toolbar {
       ToolbarItemGroup(placement: .keyboard) {
           Spacer()
           Button("Done") { /* same resignFirstResponder call */ }
       }
   }
   ```

---

## API Endpoints (Main)

### Auth
- `POST /api/auth/register`
- `POST /api/auth/login`

### Workouts
- `GET /api/workouts` - List workouts
- `POST /api/workouts` - Create workout
- `GET /api/workouts/{id}` - Get details
- `PUT /api/workouts/{id}` - Update
- `DELETE /api/workouts/{id}` - Soft delete

### Screenshot Processing
- `POST /api/screenshot/process` - Single screenshot
- `POST /api/screenshot/batch` - Multiple screenshots

### Progress
- `GET /api/progress` - XP, level, rank, stats
- `GET /api/progress/prs` - Personal records
- `GET /api/achievements` - User achievements

---

## User Profile Context (for AI coaching)

- Male, 29, 5'9", ~166 lb
- Trains ~3x/week strength + occasional cardio
- Compound-focused, moderate volume, 4-8 reps
- Key insight: Grip endurance is limiting pull-ups and deadlifts (underexposed, not weak)

### Strength Profile (estimated)
| Lift | e1RM | BW Ratio |
|------|------|----------|
| Squat | ~270 lb | 1.63x |
| Bench | ~185 lb | 1.11x |
| Row | ~170 lb | 1.02x |

---

## Session History (Summary)

| Session | Focus |
|---------|-------|
| 1 | Foundation: Backend models, project structure, documentation |
| 2 | iOS frontend (22 Swift files), data import |
| 3 | Xcode integration, JSON decoding fixes, seed data |
| 4 | XP system, 18 achievements, chart interactivity |
| 5 | Backend bug fixes (PR detection, datetime issues) |
| 6 | iOS session expiry auto-logout |
| Later | WHOOP support, batch screenshots, analytics time ranges |

---

## File Locations Summary

| What | Path |
|------|------|
| CLAUDE.md (detailed) | `fitness-app/fitness-app/CLAUDE.md` |
| Backend code | `fitness-app/fitness-app/backend/` |
| iOS code | `fitness-app/fitness-app/ios/FitnessApp/` |
| Legacy dashboard | `fitness-app/Fitness/dashboard/` |
| Strength Coach CLI | `fitness-app/Fitness/strength-coach/` |
| Session summaries | `fitness-app/fitness-app/SESSION_*.md` |

---

## Next Steps (Suggested)

1. Test iOS app with current backend
2. Add date picker for screenshot uploads (fixes WHOOP date issue)
3. Complete daily quest UI integration
4. Add PR celebration animation
5. Performance optimization

---

**Last Updated**: January 2026
