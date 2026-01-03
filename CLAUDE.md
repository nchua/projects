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
- **Git**: https://github.com/nchua/projects.git (branch: `fitness`)

```bash
git push origin main:fitness      # Deploy to Railway
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
git push origin main:fitness --force

# 6. Clean up
rm -rf .git/refs/original
git reflog expire --expire=now --all
git gc --prune=now --aggressive

# 7. CHANGE THE EXPOSED PASSWORD if used elsewhere!
```
