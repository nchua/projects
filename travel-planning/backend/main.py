"""Depart API — FastAPI application entrypoint."""

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import text

from app.api.auth import router as auth_router
from app.api.device_tokens import router as device_tokens_router
from app.api.geocoding import router as geocoding_router
from app.api.saved_locations import router as locations_router
from app.api.trips import router as trips_router
from app.api.users import router as users_router
from app.core.config import get_settings
from app.core.database import async_session
from app.core.redis import close_redis_pool, get_redis_pool

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    logger.info("Depart API starting up")
    yield
    # Shutdown: close Redis connection pool
    logger.info("Depart API shutting down, closing Redis pool")
    await close_redis_pool()


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount all routers under /api/v1
    prefix = settings.api_v1_prefix
    app.include_router(auth_router, prefix=prefix)
    app.include_router(users_router, prefix=prefix)
    app.include_router(trips_router, prefix=prefix)
    app.include_router(locations_router, prefix=prefix)
    app.include_router(device_tokens_router, prefix=prefix)
    app.include_router(geocoding_router, prefix=prefix)

    @app.get("/health")
    async def health_check() -> dict:
        """Health check endpoint — verifies DB and Redis connectivity."""
        checks: dict[str, str] = {}

        # Database check
        try:
            async with async_session() as session:
                await session.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:
            logger.error("Health check: database error: %s", exc)
            checks["database"] = "error"

        # Redis check
        try:
            r = await get_redis_pool()
            await r.ping()
            checks["redis"] = "ok"
        except Exception as exc:
            logger.error("Health check: redis error: %s", exc)
            checks["redis"] = "error"

        all_ok = all(v == "ok" for v in checks.values())
        return {
            "status": "ok" if all_ok else "degraded",
            "version": settings.app_version,
            "checks": checks,
        }

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
