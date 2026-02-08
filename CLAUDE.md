# CLAUDE.md - Fitness Tracking System

Project instructions for Claude Code when working with this codebase.

## Project Overview

A Solo Leveling-inspired fitness tracking ecosystem with:
- **iOS App**: Swift/SwiftUI frontend with gamification (XP, ranks, quests)
- **Python Backend**: FastAPI server deployed on Railway
- **Strength Coach**: CLI tool for advanced analytics
- **Legacy Dashboard**: HTML/JS fitness dashboard with screenshot processing

## Repository Structure

```
fitness-app/
├── fitness-app/              # Main iOS + Backend app
│   ├── backend/              # FastAPI backend (Python)
│   │   ├── app/
│   │   │   ├── api/          # Endpoints: auth, workouts, exercises, bodyweight, etc.
│   │   │   ├── core/         # Config, security, database, e1RM calculations
│   │   │   ├── models/       # SQLAlchemy models (User, Workout, Exercise, Set, PR)
│   │   │   ├── schemas/      # Pydantic request/response schemas
│   │   │   └── services/     # Screenshot processing service
│   │   ├── alembic/          # Database migrations
│   │   └── main.py
│   ├── ios/FitnessApp/       # iOS app (Swift/SwiftUI)
│   │   ├── Views/            # SwiftUI views (Home, Log, History, Profile, Progress)
│   │   ├── Services/         # APIClient, AuthManager, HealthKitManager
│   │   ├── Models/           # Data models
│   │   ├── Components/       # Reusable UI (XPBar, StatCard, RankBadge, etc.)
│   │   └── Utils/            # Colors, Fonts, Extensions
│   └── *.js                  # Test scripts (test-auth.js, test-workouts.js, etc.)
│
├── Fitness/                  # Legacy fitness tracking
│   ├── scripts/              # Screenshot processing Python scripts
│   ├── dashboard/            # HTML dashboard + workout_log.json
│   └── strength-coach/       # CLI analytics tool
│       └── src/strength_coach/
│           ├── models/       # Pydantic models (workout, exercise, bodyweight)
│           ├── analytics/    # e1RM, volume, trends, PRs
│           ├── storage/      # SQLite storage
│           ├── reporting/    # Markdown reports, weekly reviews
│           └── cli/          # Command-line interface
│
└── financial-analyst-agent/  # Separate project (not fitness-related)
```

## Common Commands

### Backend (FastAPI)
```bash
cd fitness-app/backend
source venv/bin/activate
python main.py                              # Run locally on port 8000
alembic upgrade head                        # Apply migrations
alembic revision --autogenerate -m "desc"   # Create migration
```

### iOS
```bash
cd fitness-app/ios
xcodegen generate                           # Regenerate Xcode project
open FitnessApp.xcodeproj                   # Open in Xcode
```

### Testing
```bash
node fitness-app/test-auth.js               # Test authentication
node fitness-app/test-workouts.js           # Test workout endpoints
node fitness-app/test-exercises.js          # Test exercise endpoints
```

### Strength Coach CLI
```bash
cd Fitness/strength-coach
pip install -e .
coach init                                  # Initialize database
coach ingest examples/sample_workout.json   # Import workout
coach add-weight 166.2 --unit lb            # Log bodyweight
coach review                                # Generate weekly review
coach lift squat                            # Check lift progress
coach prs                                   # View personal records
```

## Deployment

- **Backend**: Railway (https://backend-production-e316.up.railway.app)
- **Git**: https://github.com/nchua/projects.git
- **Auto-deploy**: Push to `main` triggers Railway deployment

```bash
git push origin main                        # Deploy to Railway
```

## Environment Variables

### Backend (Railway)
- `DATABASE_URL` - PostgreSQL connection string
- `SECRET_KEY` / `JWT_SECRET_KEY` - JWT signing key
- `ANTHROPIC_API_KEY` - For Claude Vision screenshot processing

### Local Development
- `API_BASE_URL` - Backend URL (default: localhost:8000)
- `SEED_USER_EMAIL` - Email for seed scripts
- `SEED_USER_PASSWORD` - Password for seed scripts

## Data Models

### Workout Structure
```
User
├── WorkoutSession (date, duration_minutes, session_rpe, notes)
│   └── WorkoutExercise (order_index)
│       └── Set (weight, weight_unit, reps, rpe, rir, e1rm)
├── BodyweightEntry (weight, unit, date)
└── PersonalRecord (exercise_id, weight, reps, e1rm, date)
```

### Exercise Schema
Exercises have: name, category (compound/isolation), muscle_groups, equipment, aliases

## Key Features

### Screenshot Processing
- Uses Claude Vision API to extract workout data from gym app screenshots
- Supports both gym workout and WHOOP activity screenshots
- Backend: `backend/app/services/screenshot_service.py`
- iOS: `Views/Log/ScreenshotProcessingViewModel.swift`

### e1RM Calculation
- Uses Epley formula: `weight * (1 + reps/30)`
- Calculated on backend when saving sets
- Used for PR detection and strength tracking

### Gamification
- XP system with level progression
- Rank badges (E-rank to S-rank)
- Daily quests for workout goals

---

## Security Guidelines

### NEVER Commit Credentials
- No hardcoded emails, passwords, API keys, or tokens
- Use environment variables: `os.environ.get("VAR_NAME")`
- Use placeholder values in code: `test@example.com`, `TestPass123!`

### Sensitive Files to Watch
- `backend/seed_user_data.py`
- `import_workouts.py`
- Any new seed/test scripts

---

## Workout Data Display Guidelines

When modifying workout data sources, update ALL display locations:

### Backend
1. `backend/app/schemas/workout.py` - Pydantic schemas
2. `backend/app/api/workouts.py` - API endpoints
3. `backend/app/services/screenshot_service.py` - Screenshot extraction

### iOS
1. `ios/.../Views/Home/HomeView.swift` - Recent workout card
2. `ios/.../Views/History/HistoryView.swift` - Workout history
3. `ios/.../Services/APITypes.swift` - Decodable structs

---

## Problem-Solving Guidelines

### When Auto-Fixes Fail, Add Manual Controls
Instead of debugging complex automatic behavior, give users control:
- **Timezone issues**: Let users pick the date
- **Data extraction errors**: Let users edit extracted data
- **Ambiguous inputs**: Ask users to clarify

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
