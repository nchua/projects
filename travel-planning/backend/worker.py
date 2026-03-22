"""ARQ worker for background trip monitoring and notification dispatch.

Start command: arq backend.worker.WorkerSettings
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
from arq import cron
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _parse_redis_url(url: str) -> RedisSettings:
    """Parse a Redis URL into ARQ RedisSettings."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        password=parsed.password,
        database=int(parsed.path.lstrip("/") or 0),
        ssl=parsed.scheme == "rediss",
    )


async def startup(ctx: dict[str, Any]) -> None:
    """Initialize shared resources for the worker.

    Called once when the worker process starts. Sets up:
    - Async SQLAlchemy engine + session factory
    - httpx client for Google Routes API
    - Firebase Admin SDK
    """
    settings = get_settings()

    # Database — separate pool from the API server
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_size=settings.worker_db_pool_size,
        max_overflow=settings.worker_db_max_overflow,
        pool_pre_ping=True,
    )
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    ctx["db_engine"] = engine
    ctx["db_session"] = session_factory

    # HTTP client for Google Routes API (connection pooling)
    ctx["http_client"] = httpx.AsyncClient(
        timeout=httpx.Timeout(10.0, connect=5.0),
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )

    # Google Routes client
    from app.services.google_routes import GoogleRoutesClient

    ctx["routes_client"] = GoogleRoutesClient(
        api_key=settings.google_routes_api_key,
        http_client=ctx["http_client"],
    )

    # Firebase Admin SDK
    _init_firebase(settings)

    logger.info("Worker startup complete")


def _init_firebase(settings: Any) -> None:
    """Initialize Firebase Admin SDK from credentials."""
    try:
        import firebase_admin
        from firebase_admin import credentials

        if firebase_admin._apps:
            return  # Already initialized

        if settings.firebase_credentials_json:
            cred_dict = json.loads(settings.firebase_credentials_json)
            cred = credentials.Certificate(cred_dict)
        elif settings.firebase_credentials_path:
            cred = credentials.Certificate(settings.firebase_credentials_path)
        else:
            logger.warning(
                "No Firebase credentials configured — push notifications disabled"
            )
            return

        firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialized")
    except Exception:
        logger.exception("Failed to initialize Firebase Admin SDK")


async def shutdown(ctx: dict[str, Any]) -> None:
    """Clean up shared resources on worker shutdown."""
    if "http_client" in ctx:
        await ctx["http_client"].aclose()

    if "db_engine" in ctx:
        await ctx["db_engine"].dispose()

    logger.info("Worker shutdown complete")


# Import job functions — these are registered after definition
# to avoid circular imports at module level
async def _check_trip_eta(ctx: dict[str, Any], trip_id: str) -> None:
    """Check ETA for a single trip via Google Routes API."""
    from app.services.traffic_checker import check_trip_eta

    await check_trip_eta(ctx, trip_id)


async def _evaluate_alert(
    ctx: dict[str, Any], trip_id: str, new_eta_seconds: int
) -> None:
    """Evaluate whether to send a notification for a trip."""
    from app.services.alert_evaluator import evaluate_alert

    await evaluate_alert(ctx, trip_id, new_eta_seconds)


async def _send_push_notification(
    ctx: dict[str, Any],
    trip_id: str,
    tier: str,
    departure_time_iso: str,
    silent: bool = False,
    change_direction: str = "initial",
) -> None:
    """Send a push notification for a trip."""
    from app.services.push_sender import send_push_notification

    await send_push_notification(
        ctx, trip_id, tier, departure_time_iso, silent, change_direction
    )


async def _scan_active_trips(ctx: dict[str, Any]) -> None:
    """Cron job: scan trips and enqueue ETA checks."""
    from app.services.trip_scanner import scan_active_trips

    await scan_active_trips(ctx)


async def _cleanup_expired_trips(ctx: dict[str, Any]) -> None:
    """Cron job: mark expired trips as completed."""
    from app.services.trip_scanner import cleanup_expired_trips

    await cleanup_expired_trips(ctx)


async def _health_check(ctx: dict[str, Any]) -> None:
    """Cron job: write heartbeat to Redis."""
    from app.services.health_check import worker_health_check

    await worker_health_check(ctx)


class WorkerSettings:
    """ARQ worker configuration."""

    redis_settings = _parse_redis_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    )

    functions = [
        _check_trip_eta,
        _evaluate_alert,
        _send_push_notification,
    ]

    cron_jobs = [
        cron(_scan_active_trips, second=0),  # Every 60s
        cron(_cleanup_expired_trips, minute=0),  # Every hour
        cron(_health_check, second={0, 30}),  # Every 30s
    ]

    max_jobs = 50
    job_timeout = 30
    max_tries = 3
    retry_delay = 5

    on_startup = startup
    on_shutdown = shutdown
