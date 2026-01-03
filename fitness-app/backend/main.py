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
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)}
    )

# Configure CORS for iOS app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """Root endpoint - API information"""
    return {
        "message": "Fitness Tracker API",
        "version": "0.2.1-pr-fix",
        "status": "running",
        "docs": "/docs",
        "deploy_check": "2026-01-03-batch-screenshots"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "ok",
        "app": settings.APP_NAME
    }


# Debug endpoint to add sports exercises
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
from app.api import auth, profile, exercises, workouts, bodyweight, analytics, sync, progress, quests, screenshot, activity
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(profile.router, prefix="/profile", tags=["Profile"])
app.include_router(exercises.router, prefix="/exercises", tags=["Exercises"])
app.include_router(workouts.router, prefix="/workouts", tags=["Workouts"])
app.include_router(bodyweight.router, prefix="/bodyweight", tags=["Bodyweight"])
app.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
app.include_router(sync.router, prefix="/sync", tags=["Sync"])
app.include_router(progress.router, prefix="/progress", tags=["Progress"])
app.include_router(quests.router, prefix="/quests", tags=["Quests"])
app.include_router(screenshot.router, prefix="/screenshot", tags=["Screenshot"])
app.include_router(activity.router, prefix="/activity", tags=["Activity"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )

