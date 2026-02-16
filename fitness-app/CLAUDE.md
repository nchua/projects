# CLAUDE.md - Fitness App

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

## Build & Validation

**IMPORTANT: After every iOS code change, run the build check. Fix all errors before committing.**

```bash
# 1. Regenerate project (if new files added)
cd ios && xcodegen generate

# 2. Build check (simulator, no signing needed)
xcodebuild -project ios/FitnessApp.xcodeproj -scheme FitnessApp \
  -destination 'generic/platform=iOS Simulator' build 2>&1 | tail -30

# 3. Quick error grep
xcodebuild -project ios/FitnessApp.xcodeproj -scheme FitnessApp \
  -destination 'generic/platform=iOS Simulator' build 2>&1 | grep "error:"

# 4. Lint entitlements
bash ios/scripts/lint-entitlements.sh
```

After committing iOS changes, remind the user to rebuild in Xcode (Cmd+R).
Backend-only changes don't need an Xcode rebuild — just push to Railway or restart the local server.

---

## iOS Rules

### Entitlements: No Apple Pay
`com.apple.developer.in-app-payments` must NEVER be in `project.yml` or `.entitlements`.
StoreKit 2 IAPs only need `InAppPurchase` — not the Apple Pay entitlement.

### fullScreenCover: Always use .id() when iterating through items
- Prevents black screens from stale `@State`
- Always include else branch that cleans up all state
- Guard double dismissal with `isDismissed` flag

### .onChange: Guard against infinite loops
- Track processed response IDs to detect re-entry
- Clear tracking flag in skip branch

### View Naming: Use {DesignSystem}{DataType}{ComponentType}
- Prevents duplicate struct name build errors
- Search before creating: `grep -r "struct YourStructName" ios/`

---

## Deployment

- **Backend**: Railway (https://backend-production-e316.up.railway.app)
- **Git**: https://github.com/nchua/projects.git
- **Branch**: `main` (auto-deploys on push)

## Environment Variables

### Backend (Railway)
- `DATABASE_URL` - PostgreSQL connection string
- `JWT_SECRET_KEY` - JWT signing key
- `ANTHROPIC_API_KEY` - For screenshot processing

### Local Scripts
- `API_BASE_URL` - Backend URL (default: localhost:8000)
- `SEED_USER_EMAIL` / `SEED_USER_PASSWORD` - For seed scripts

---

## Git Safety

**ALWAYS check branch and status before destructive operations** (deleting files, resetting commits, force pushing, major refactors).

---

## Security

NEVER hardcode credentials. Use `os.environ.get("VAR_NAME")` and placeholder values (`test@example.com`, `TestPass123!`).

---

## SQLAlchemy: Always Use joinedload Before Passing to Services

After `db.commit()` + `db.refresh()`, relationship collections are **empty**. Always re-query with `joinedload()` before passing models to service functions that access relationships (`update_quest_progress()`, `update_dungeon_progress()`, `check_and_unlock_achievements()`).

---

## Workout Data Display Guidelines

When modifying how workout data is fetched, stored, or structured, update ALL display locations:

**Backend:** `schemas/workout.py` → `api/workouts.py` → `services/screenshot_service.py`
**iOS:** `APITypes.swift` → `HomeView.swift` → `HistoryView.swift`

### Checklist When Adding New Workout Fields
- [ ] Add field to backend Pydantic schema (`schemas/workout.py`)
- [ ] Update backend API endpoint (`api/workouts.py`)
- [ ] Add field to iOS Decodable struct (`APITypes.swift`)
- [ ] Update iOS views (`HomeView.swift`, `HistoryView.swift`)
- [ ] If screenshot-related, update `screenshot_service.py` and `schemas/screenshot.py`

---

## Open Decisions

### When to request notification permission (Phase 3)
`NotificationManager.requestAuthorization()` exists but is not called anywhere yet.
Decide when to prompt — options: after first workout, on first launch, from settings screen, or after onboarding.
Files: `ios/FitnessApp/Services/NotificationManager.swift`, wherever the trigger is added.
