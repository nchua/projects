"""
Fitness Tracker API - Main application entry point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import engine, Base
from app import models  # Import models to register them

# Create database tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.APP_NAME,
    description="API for fitness tracking iOS app with workout logging, analytics, and progress tracking",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
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
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "ok",
        "app": settings.APP_NAME
    }

# Import and include API routers
from app.api import auth, profile, exercises, workouts, bodyweight, analytics, sync, progress, quests
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(profile.router, prefix="/profile", tags=["Profile"])
app.include_router(exercises.router, prefix="/exercises", tags=["Exercises"])
app.include_router(workouts.router, prefix="/workouts", tags=["Workouts"])
app.include_router(bodyweight.router, prefix="/bodyweight", tags=["Bodyweight"])
app.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
app.include_router(sync.router, prefix="/sync", tags=["Sync"])
app.include_router(progress.router, prefix="/progress", tags=["Progress"])
app.include_router(quests.router, prefix="/quests", tags=["Quests"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )
