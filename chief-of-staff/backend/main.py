"""Chief of Staff API — Main application entry point."""

import logging
import sys

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.api import auth

# Logging must be configured before first use
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
for handler in logging.root.handlers:
    handler.flush = sys.stdout.flush

logger = logging.getLogger(__name__)

settings = get_settings()

if settings.secret_key == "change-me-to-a-random-secret-key":
    logger.warning(
        "SECRET_KEY is set to the insecure default. "
        "Set SECRET_KEY environment variable before "
        "deploying to production."
    )

app = FastAPI(
    title=settings.app_name,
    description=(
        "Personal chief of staff — briefings, "
        "tasks, and AI-powered action items"
    ),
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    """Log and return 422 validation errors."""
    logger.warning(
        "Validation error on %s: %s",
        request.url.path, exc.errors(),
    )
    return JSONResponse(
        status_code=422, content={"detail": exc.errors()}
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    """Log and return HTTP exceptions."""
    logger.info(
        "HTTP %d on %s: %s",
        exc.status_code, request.url.path, exc.detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Catch-all for unhandled exceptions."""
    logger.exception(
        "Unhandled exception on %s", request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
    }


app.include_router(
    auth.router,
    prefix=f"{settings.api_v1_prefix}/auth",
    tags=["Authentication"],
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app", host="0.0.0.0", port=8000, reload=True
    )
