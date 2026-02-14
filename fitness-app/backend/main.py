"""
Fitness Tracker API - Main application entry point
"""
import logging
import sys

# Configure logging to stdout for Railway
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
# Ensure logs are flushed immediately
for handler in logging.root.handlers:
    handler.flush = sys.stdout.flush

logger = logging.getLogger(__name__)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import engine, Base
from app import models  # Import models to register them

# Run alembic migrations on startup
import subprocess
import os
try:
    print("Running database migrations...")
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        print("Migrations completed successfully")
    else:
        print(f"Migration warning: {result.stderr}")
        # Fall back to create_all for new tables
        Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"Migration error: {e}")
    # Fall back to create_all
    Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.APP_NAME,
    description="API for fitness tracking iOS app with workout logging, analytics, and progress tracking",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add validation error handler to log details
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    print(f"VALIDATION ERROR on {request.url.path}: {exc.errors()}", flush=True)
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()}
    )

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    print(f"HTTP EXCEPTION on {request.url.path}: status={exc.status_code}, detail={exc.detail}", flush=True)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    print(f"GENERAL EXCEPTION on {request.url.path}: {type(exc).__name__}: {exc}", flush=True)
    detail = str(exc) if settings.DEBUG else "Internal server error"
    return JSONResponse(
        status_code=500,
        content={"detail": detail}
    )

# Configure CORS — iOS native apps don't send Origin headers,
# so CORS doesn't apply to mobile requests. This covers web clients.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://backend-production-e316.up.railway.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Debug middleware to log all requests/responses
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

class DebugMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        import sys
        sys.stderr.write(f"REQUEST: {request.method} {request.url.path}\n")
        sys.stderr.flush()
        try:
            response = await call_next(request)
            sys.stderr.write(f"RESPONSE: {request.url.path} -> {response.status_code}\n")
            sys.stderr.flush()
            return response
        except Exception as e:
            sys.stderr.write(f"MIDDLEWARE EXCEPTION: {request.url.path} -> {type(e).__name__}: {e}\n")
            sys.stderr.flush()
            raise

if settings.DEBUG:
    app.add_middleware(DebugMiddleware)

@app.get("/")
async def root():
    """Root endpoint - API information"""
    return {
        "message": "Fitness Tracker API",
        "version": "0.3.0-multi-goal",
        "status": "running",
        "docs": "/docs",
        "deploy_check": "2026-02-02-multi-goal-missions"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "ok",
        "app": settings.APP_NAME
    }


@app.get("/privacy")
async def privacy_policy():
    """Serve the privacy policy page"""
    from fastapi.responses import HTMLResponse
    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ARISE - Privacy Policy</title>
<style>
  body { background: #0a0a0f; color: #c8ccd4; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; line-height: 1.7; margin: 0; padding: 20px; }
  .container { max-width: 700px; margin: 0 auto; padding: 24px 0; }
  h1 { color: #00e5ff; font-size: 24px; letter-spacing: 2px; text-transform: uppercase; border-bottom: 1px solid #1a1a2e; padding-bottom: 16px; }
  h2 { color: #e0e0e0; font-size: 16px; letter-spacing: 1px; text-transform: uppercase; margin-top: 32px; }
  p, li { font-size: 14px; color: #9a9eb0; }
  ul { padding-left: 20px; }
  a { color: #00e5ff; text-decoration: none; }
  .updated { font-size: 12px; color: #555; margin-top: 40px; border-top: 1px solid #1a1a2e; padding-top: 16px; }
</style>
</head>
<body>
<div class="container">
<h1>ARISE Privacy Policy</h1>
<p>ARISE ("we", "our", "the app") is a fitness tracking application. This policy describes how we collect, use, and protect your data.</p>

<h2>Data We Collect</h2>
<ul>
  <li><strong>Account information:</strong> Email address and hashed password for authentication.</li>
  <li><strong>Workout data:</strong> Exercises, sets, reps, weights, and session details you log.</li>
  <li><strong>Body metrics:</strong> Bodyweight entries, age, sex, and height you optionally provide.</li>
  <li><strong>Apple Health data:</strong> Steps, calories, and activity data synced with your permission via HealthKit.</li>
  <li><strong>Photos:</strong> Workout screenshots you upload for AI-powered data extraction. Images are processed and not permanently stored.</li>
</ul>

<h2>How We Use Your Data</h2>
<ul>
  <li>To provide fitness tracking, progress analytics, and personal records.</li>
  <li>To extract workout data from screenshots using AI (Anthropic Claude API).</li>
  <li>To calculate strength metrics and generate weekly reports.</li>
</ul>

<h2>Third-Party Services</h2>
<ul>
  <li><strong>Anthropic Claude API:</strong> Processes uploaded workout screenshots to extract exercise data. Images are sent to Anthropic's API and are subject to <a href="https://www.anthropic.com/privacy">Anthropic's privacy policy</a>.</li>
  <li><strong>Railway:</strong> Hosts our backend infrastructure. Data is stored on Railway's servers.</li>
</ul>

<h2>Data Storage &amp; Retention</h2>
<p>Your data is stored in a PostgreSQL database hosted on Railway. We retain your data for as long as your account is active. Deleted accounts are soft-deleted immediately and permanently removed after 30 days.</p>

<h2>Your Rights</h2>
<ul>
  <li><strong>Access:</strong> You can view all your data through the app.</li>
  <li><strong>Deletion:</strong> You can delete your account from the Profile screen. All data will be permanently removed after 30 days.</li>
  <li><strong>Export:</strong> Contact us to request a copy of your data.</li>
</ul>

<h2>Security</h2>
<p>Passwords are hashed using bcrypt. All communication uses HTTPS/TLS encryption. Authentication uses JWT tokens.</p>

<h2>Children</h2>
<p>ARISE is not intended for users under 13. We do not knowingly collect data from children.</p>

<h2>Contact</h2>
<p>For privacy inquiries, contact us at <a href="mailto:privacy@arise-fitness.app">privacy@arise-fitness.app</a>.</p>

<p class="updated">Last updated: February 14, 2026</p>
</div>
</body>
</html>"""
    return HTMLResponse(content=html)


# Debug endpoint to add sports exercises
if settings.DEBUG:
    @app.post("/debug/add-sports")
    async def add_sports_exercises_endpoint():
        """Add sports and cardio exercises to the database"""
        from app.core.database import SessionLocal
        from add_sports_exercises import add_sports_exercises
        db = SessionLocal()
        try:
            add_sports_exercises(db)
            return {"status": "ok", "message": "Sports exercises added"}
        finally:
            db.close()

# Import and include API routers
from app.api import auth, profile, exercises, workouts, bodyweight, analytics, sync, progress, quests, screenshot, activity, dungeons, users, friends, password_reset, goals, missions, weekly_report
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(password_reset.router, prefix="/auth/password-reset", tags=["Password Reset"])
app.include_router(profile.router, prefix="/profile", tags=["Profile"])
app.include_router(users.router, prefix="/users", tags=["Users"])
app.include_router(exercises.router, prefix="/exercises", tags=["Exercises"])
app.include_router(workouts.router, prefix="/workouts", tags=["Workouts"])
app.include_router(bodyweight.router, prefix="/bodyweight", tags=["Bodyweight"])
app.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
app.include_router(sync.router, prefix="/sync", tags=["Sync"])
app.include_router(progress.router, prefix="/progress", tags=["Progress"])
app.include_router(quests.router, prefix="/quests", tags=["Quests"])
app.include_router(screenshot.router, prefix="/screenshot", tags=["Screenshot"])
app.include_router(activity.router, prefix="/activity", tags=["Activity"])
app.include_router(dungeons.router, prefix="/dungeons", tags=["Dungeons"])
app.include_router(friends.router, prefix="/friends", tags=["Friends"])
app.include_router(goals.router, prefix="/goals", tags=["Goals"])
app.include_router(missions.router, prefix="/missions", tags=["Missions"])
app.include_router(weekly_report.router, prefix="/progress", tags=["Progress"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )

