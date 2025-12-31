# Next Steps for Future Agents

## Quick Start

The foundation is complete! Here's how to pick up where we left off:

### 1. Set Up Development Environment

```bash
# Run the initialization script
./init.sh

# This will:
# - Create Python virtual environment
# - Install all dependencies
# - Create .env file
# - Offer to start the backend server
```

### 2. Create Database Tables

```bash
cd backend
source venv/bin/activate

# Generate initial migration from models
alembic revision --autogenerate -m "Initial database schema"

# Apply migration to create tables
alembic upgrade head

# Verify tables created
python -c "from app.core.database import engine; from sqlalchemy import inspect; print(inspect(engine).get_table_names())"
```

### 3. Test Backend Health Check

```bash
# Start the backend (from backend directory)
python main.py

# In another terminal, test endpoints:
curl http://localhost:8000/
curl http://localhost:8000/health
curl http://localhost:8000/docs  # Interactive API documentation
```

If these work, mark this feature as passing:
- ✅ "Backend initialization: Set up FastAPI project structure with basic health check"

## Priority Order for Implementation

Work through `feature_list.json` in order. Here's the recommended sequence:

### Phase 1: Backend Core (Features 1-4)
1. ✅ Backend initialization (test with health check)
2. Database setup (generate and run migrations)
3. Database setup backend (PostgreSQL models - already done with SQLite)
4. Exercise library seed data

### Phase 2: Authentication (Features 6-8)
5. POST /auth/register endpoint
6. POST /auth/login endpoint with JWT
7. POST /auth/refresh endpoint

### Phase 3: User Profile (Feature 9)
8. GET /profile and PUT /profile endpoints

### Phase 4: Exercise Endpoints (Features 10-11)
9. GET /exercises with filtering
10. POST /exercises for custom exercises

### Phase 5: Workout Logging (Features 12-16)
11. POST /workouts - Create workout
12. GET /workouts - List with pagination
13. GET /workouts/{id} - Get details
14. PUT /workouts/{id} - Update
15. DELETE /workouts/{id} - Delete

### Phase 6: Analytics Engine (Features 17-27)
16. e1RM calculations (Epley formula)
17. Multiple e1RM formulas (Brzycki, Wathan, Lombardi)
18. GET /analytics/exercise/{id}/trend
19. GET /analytics/exercise/{id}/history
20. GET /analytics/percentiles
21. PR detection (e1RM)
22. PR detection (rep PRs)
23. GET /analytics/prs
24. Bodyweight tracking
25. Bodyweight history with rolling averages
26. Insights generation
27. Weekly review

### Phase 7: Sync (Features 28-29)
28. POST /sync bulk endpoint
29. GET /sync/status

### Phase 8: iOS Frontend (Features 30-46)
30. Home screen dashboard
31. Workout logging screen
32. Set logging form
33. Rest timer
34. Auto-save to local DB
35. History screen with calendar
36. History list with detail sheets
37. Progress screen with e1RM chart
38. Volume bar chart
39. Percentile gauges
40. PR timeline
41. Profile screen
42. Offline functionality
43. Background sync
44. Conflict resolution
45. Pull-to-refresh
46. Copy workout as template
47. Favorite exercises
48. e1RM calculator tool

### Phase 9: Design & Polish (Features 49-56)
49. Dark color palette
50. Typography (SF Pro)
51. Rounded cards
52. Haptic feedback
53. Chart animations
54. Responsive layouts
55. Performance - Charts load < 1s
56. Performance - Log set < 5s
57. End-to-end user journey test

## Implementation Tips

### For Backend Features

1. **Create the endpoint file** in `backend/app/api/`
   ```python
   # Example: backend/app/api/auth.py
   from fastapi import APIRouter, Depends, HTTPException
   from sqlalchemy.orm import Session
   from app.core.database import get_db

   router = APIRouter()

   @router.post("/register")
   async def register(data: RegisterSchema, db: Session = Depends(get_db)):
       # Implementation
       pass
   ```

2. **Create Pydantic schemas** in `backend/app/schemas/`
   ```python
   # Example: backend/app/schemas/auth.py
   from pydantic import BaseModel, EmailStr

   class RegisterSchema(BaseModel):
       email: EmailStr
       password: str
   ```

3. **Create business logic** in `backend/app/services/`
   ```python
   # Example: backend/app/services/auth.py
   def create_user(db: Session, email: str, password: str):
       # Implementation
       pass
   ```

4. **Include router in main.py**
   ```python
   from app.api import auth
   app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
   ```

5. **Test with curl or httpx**
   ```bash
   curl -X POST http://localhost:8000/auth/register \
     -H "Content-Type: application/json" \
     -d '{"email": "test@example.com", "password": "securepass"}'
   ```

6. **Mark feature as passing** in feature_list.json ONLY when all test steps pass

### For iOS Features

1. **Create Xcode project** following `ios/README.md`

2. **Set up SwiftData or GRDB** for local database

3. **Create models** matching backend schema

4. **Implement API client** with URLSession

5. **Build views** following design system in spec

6. **Test on simulator** following feature test steps

7. **Mark feature as passing** when fully working

## Testing Features

For each feature in feature_list.json:

1. Read the description and steps carefully
2. Implement the feature
3. Follow EVERY step in the test
4. Only change `"passes": false` to `"passes": true` when ALL steps pass
5. NEVER remove or edit features - only mark as passing
6. Commit after each feature completion

## Seed Data

Create seed data for exercise library (Feature 5). Example:

```python
# backend/seed_exercises.py
from app.core.database import SessionLocal, engine
from app.models import Exercise, Base

Base.metadata.create_all(bind=engine)

exercises = [
    {"name": "Squat", "canonical_id": "squat", "category": "Legs", "primary_muscle": "Quadriceps"},
    {"name": "Back Squat", "canonical_id": "squat", "category": "Legs", "primary_muscle": "Quadriceps"},
    {"name": "Bench Press", "canonical_id": "bench", "category": "Push", "primary_muscle": "Chest"},
    {"name": "Deadlift", "canonical_id": "deadlift", "category": "Pull", "primary_muscle": "Back"},
    # Add 46+ more exercises...
]

db = SessionLocal()
for ex in exercises:
    db.add(Exercise(**ex, is_custom=False))
db.commit()
```

## Git Workflow

1. Work on ONE feature at a time
2. Test thoroughly
3. Update feature_list.json to mark as passing
4. Commit with clear message: `"Implement [feature]: [description]"`
5. Update claude-progress.txt
6. Move to next feature

## Monitoring Progress

```bash
# View all features
cat feature_list.json | jq '.[] | {description: .description, passes: .passes}'

# Count completed
cat feature_list.json | jq '[.[] | select(.passes == true)] | length'

# View next feature to implement
cat feature_list.json | jq '.[] | select(.passes == false) | .description' | head -1
```

## Important Reminders

- ⚠️ **NEVER** remove or edit features in feature_list.json
- ⚠️ **ONLY** change `"passes": false` to `"passes": true`
- ⚠️ Test ALL steps before marking as passing
- ⚠️ Commit frequently with descriptive messages
- ⚠️ Update claude-progress.txt at end of each session

## Resources

- **Spec**: `app_spec.txt` - Complete project specification
- **Features**: `feature_list.json` - All 56 test cases
- **API Docs**: http://localhost:8000/docs (when backend running)
- **Progress**: `claude-progress.txt` - Session notes
- **This File**: Instructions for next steps

Good luck! The foundation is solid. Focus on quality over speed. 🏋️
