"""ARQ worker for background sync, extraction, and briefing generation.

Start command: arq worker.WorkerSettings
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from arq import cron
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.database import get_async_database_url
from app.core.redis import parse_redis_url

logger = logging.getLogger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    """Initialize shared resources for the worker."""
    settings = get_settings()

    engine = create_async_engine(
        get_async_database_url(),
        echo=False,
        pool_size=settings.worker_db_pool_size,
        max_overflow=settings.worker_db_max_overflow,
        pool_pre_ping=True,
    )
    ctx["db_engine"] = engine
    ctx["db_session"] = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    ctx["http_client"] = httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, connect=10.0),
        limits=httpx.Limits(
            max_connections=20, max_keepalive_connections=10
        ),
    )
    ctx["settings"] = settings

    logger.info("Worker startup complete")


async def shutdown(ctx: dict[str, Any]) -> None:
    """Clean up shared resources on worker shutdown."""
    if "http_client" in ctx:
        await ctx["http_client"].aclose()
    if "db_engine" in ctx:
        await ctx["db_engine"].dispose()
    logger.info("Worker shutdown complete")


# --- Job wrappers (lazy imports to avoid circular deps) ---


async def _scan_integrations(ctx: dict[str, Any]) -> None:
    """Cron: scan integrations and enqueue sync jobs."""
    from app.services.integration_scanner import (
        scan_integrations,
    )
    await scan_integrations(ctx)


async def _sync_integration(
    ctx: dict[str, Any], integration_id: str
) -> None:
    """Job: sync a single integration."""
    from app.services.integration_scanner import (
        sync_integration,
    )
    await sync_integration(ctx, integration_id)


async def _process_new_messages(
    ctx: dict[str, Any],
    integration_id: str,
    user_id: str,
    messages: list[dict],
) -> None:
    """Job: run AI extraction on new messages."""
    from app.services.message_processor import (
        process_new_messages,
    )
    await process_new_messages(
        ctx, integration_id, user_id, messages
    )


async def _generate_morning_briefings(
    ctx: dict[str, Any],
) -> None:
    """Cron: generate morning briefings for all users."""
    from app.services.briefing_cron import (
        generate_morning_briefings,
    )
    await generate_morning_briefings(ctx)


async def _cleanup_old_data(ctx: dict[str, Any]) -> None:
    """Cron: purge old sync data and archive stale items."""
    from app.services.data_cleanup import cleanup_old_data
    await cleanup_old_data(ctx)


async def _health_check(ctx: dict[str, Any]) -> None:
    """Cron: write heartbeat to Redis for monitoring."""
    from arq.connections import ArqRedis
    pool: ArqRedis = ctx["redis"]
    await pool.set(
        "chief-of-staff:worker:heartbeat",
        "alive",
        ex=60,
    )


class WorkerSettings:
    """ARQ worker configuration."""

    redis_settings = parse_redis_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    )

    functions = [
        _sync_integration,
        _process_new_messages,
    ]

    cron_jobs = [
        # Every 5 min during active hours
        cron(
            _scan_integrations,
            minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55},
        ),
        # 7am daily (job checks per-user timezone)
        cron(_generate_morning_briefings, hour=7, minute=0),
        # 3am daily
        cron(_cleanup_old_data, hour=3, minute=0),
        # Every 30s
        cron(_health_check, second={0, 30}),
    ]

    max_jobs = 50
    job_timeout = 60
    max_tries = 3
    retry_delay = 10

    on_startup = startup
    on_shutdown = shutdown
