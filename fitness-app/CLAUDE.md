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

### Backend-Only Changes: When Rebuild Is NOT Needed

If changes are **backend-only** (FastAPI/services/schemas) and **no iOS Swift files changed**, the app **does not need an Xcode rebuild**.

**What the user needs to do instead:**
- **Using Railway/production backend**: Push to `main` and wait for deploy, then **re-open the app or refresh** the relevant screen.
- **Using local backend**: Restart the backend (`python main.py`) and then **re-open or refresh** the app screen.

**Rule of thumb for responses**:
- If any Swift files changed → remind to rebuild in Xcode.
- If only backend changed → say pushing/restarting backend is sufficient.

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

---

## SQLAlchemy: Always Use joinedload Before Passing to Services

After `db.commit()` + `db.refresh()`, relationship collections are **empty**. Always re-query with `joinedload()` before passing models to service functions that access relationships (`update_quest_progress()`, `update_dungeon_progress()`, `check_and_unlock_achievements()`).

---

## Workout Data Display Guidelines

### IMPORTANT: When Changing Workout Data Sources

When modifying how workout data is fetched, stored, or structured, you MUST update ALL places that display workout information:

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

Instead of debugging complex automatic behavior, add a **manual override option** that gives users direct control.

**When to consider manual controls**:
1. **Timezone/date issues** - Let users pick the date instead of auto-detecting
2. **Data extraction errors** - Let users edit/correct extracted data
3. **Ambiguous inputs** - Ask users to clarify rather than guessing
4. **Environment-dependent behavior** - Server vs client differences

**Implementation pattern**:
```
Before: Auto-process → Save with auto-detected values → User sees wrong result
After:  Show preview → User adjusts values → Process with user's values → Correct result
```

---

## SwiftUI Rules (Quick Reference)

### fullScreenCover: Always use .id() when iterating through items
- Prevents black screens from stale `@State`
- Always include else branch that cleans up all state
- Guard double dismissal with `isDismissed` flag
- Lint: `ios/scripts/lint-fullscreen-cover.sh`

### .onChange: Guard against infinite loops
- Track processed response IDs to detect re-entry
- Clear tracking flag in skip branch
- Test full multi-step flows end-to-end

### View Naming: Use {DesignSystem}{DataType}{ComponentType}
- Prevents duplicate struct name build errors
- Search before creating: `grep -r "struct YourStructName" ios/`

---

## Claude Code Best Practices (Boris Cherny)

Tips from the creator of Claude Code for effective usage. Run `/best-practices` to review.

### 1. Start Complex Tasks in Plan Mode
- Pour energy into the plan so Claude can 1-shot the implementation
- Use `/plan` or ask Claude to plan before implementing
- Switch back to planning when issues arise rather than continuing forward

### 2. Invest in CLAUDE.md
- After each correction, instruct Claude to update CLAUDE.md to prevent recurring mistakes
- Maintain a notes directory for every task and reference it in documentation
- This file is your persistent memory across sessions

### 3. Create Reusable Skills
- Build custom skills and commit them to git
- Automate repetitive tasks (performed multiple times daily) with slash commands
- Include tech debt cleanup and context synchronization tools

### 4. Let Claude Fix Bugs Independently
- Use high-level instructions like "fix" or "Go fix the failing CI tests"
- Don't micromanage implementation details
- Enable MCP integrations to paste bug threads directly

### 5. Level Up Your Prompting
- Challenge Claude as a reviewer
- Ask it to implement "the elegant solution"
- Provide detailed specifications upfront to reduce ambiguity

### 6. Optimize Terminal & Environment
- Use a performant terminal (Ghostty recommended)
- Customize status bars with `/statusline`
- Color-code terminal tabs for different worktrees
- Use voice dictation for more detailed prompts

### 7. Use Subagents
- Append "use subagents" for compute-intensive requests
- Offload tasks to keep your main agent's context focused

### 8. Use Claude for Data & Analytics
- Leverage CLI tools like BigQuery within Claude Code
- Build reusable skills for analytics queries instead of writing SQL manually

### 9. Learning with Claude
- Enable "Explanatory" or "Learning" output styles in `/config`
- Request HTML presentations, ASCII diagrams for complex concepts
- Build spaced-repetition learning skills

---

## API Endpoints Reference

### Authentication
- `POST /api/auth/register` - Create account
- `POST /api/auth/login` - Get JWT token

### Workouts
- `GET /api/workouts` - List user workouts
- `POST /api/workouts` - Create workout session
- `GET /api/workouts/{id}` - Get workout details
- `PUT /api/workouts/{id}` - Update workout
- `DELETE /api/workouts/{id}` - Soft delete workout

### Exercises
- `GET /api/exercises` - List all exercises
- `GET /api/exercises/search?q=` - Search exercises

### Progress
- `GET /api/progress/summary` - Overall stats
- `GET /api/progress/prs` - Personal records

### Screenshot Processing
- `POST /api/screenshot/process` - Process single screenshot
- `POST /api/screenshot/batch` - Process multiple screenshots
