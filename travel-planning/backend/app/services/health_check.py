"""Worker health check — heartbeat and monitoring.

The health_check cron runs every 30s, writes a heartbeat to Redis,
and checks for anomalies (high failure rates, cost overruns).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Alert thresholds
MAX_DAILY_API_COST_USD = 10.0
GOOGLE_COST_PER_CALL_USD = 0.01  # $10 per 1000 calls
HEALTH_KEY = "worker:health"
HEALTH_TTL = 120  # 2 minutes


async def worker_health_check(ctx: dict[str, Any]) -> None:
    """Cron job: write heartbeat and check system health."""
    redis = ctx["redis"]
    now = datetime.now(timezone.utc)

    # Write heartbeat
    await redis.setex(HEALTH_KEY, HEALTH_TTL, now.isoformat())

    # Check daily API cost
    date_str = now.strftime("%Y-%m-%d")
    daily_calls = await redis.get(f"metrics:api_calls:{date_str}")
    if daily_calls:
        estimated_cost = int(daily_calls) * GOOGLE_COST_PER_CALL_USD
        if estimated_cost > MAX_DAILY_API_COST_USD:
            logger.warning(
                f"Daily API cost estimate: ${estimated_cost:.2f} "
                f"({daily_calls} calls) — exceeds ${MAX_DAILY_API_COST_USD} threshold"
            )
            await _send_alert(
                ctx,
                f"API cost alert: ${estimated_cost:.2f} today ({daily_calls} calls)",
            )

    logger.debug(f"Health check OK at {now.isoformat()}")


async def _send_alert(ctx: dict[str, Any], message: str) -> None:
    """Send an alert via Slack webhook (if configured)."""
    from app.core.config import get_settings

    settings = get_settings()
    webhook_url = getattr(settings, "slack_webhook_url", "")

    if not webhook_url:
        logger.warning(f"Alert (no webhook configured): {message}")
        return

    try:
        http_client = ctx.get("http_client")
        if http_client is None:
            async with httpx.AsyncClient() as client:
                await client.post(
                    webhook_url,
                    json={
                        "text": f":warning: Depart Worker Alert: {message}"
                    },
                    timeout=5.0,
                )
        else:
            await http_client.post(
                webhook_url,
                json={
                    "text": f":warning: Depart Worker Alert: {message}"
                },
                timeout=5.0,
            )
    except Exception:
        logger.exception(f"Failed to send Slack alert: {message}")
