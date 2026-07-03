"""511.org upstream client.

Everything here exists to respect the 60 requests / rolling hour key limit:
lazy fetches only, per-endpoint TTL cache, a stampede lock, a rolling-hour
call guard, and serve-last-good-as-stale on any failure — all via the shared
app.upstream machinery, with a call log/guard private to this feed.

Cache and lock identities are logical endpoint names — the keyed URL (which
carries the API key) exists only inside _fetch, so the secret never appears
in cache keys, lock keys, or exception messages.
"""

from __future__ import annotations

import json
import os
from datetime import datetime

from app.upstream import Upstream, UpstreamNeverFetchedError

__all__ = [
    "UpstreamNeverFetchedError",
    "get_stop_monitoring",
    "get_service_alerts",
    "upstream_calls_last_hour",
    "cache_status",
    "reset",
]

BASE_URL = "https://api.511.org/transit"

STOP_MONITORING_TTL_S = 60
ALERTS_TTL_S = 300
RATE_GUARD_MAX_CALLS_PER_HOUR = 55
UPSTREAM_TIMEOUT_S = 10

_upstream = Upstream(
    guard_max_calls_per_hour=RATE_GUARD_MAX_CALLS_PER_HOUR,
    timeout_s=UPSTREAM_TIMEOUT_S,
)

# Same deque as _upstream's (reset() clears in place, never reassigns) —
# existing tests seed/inspect the call log through this module-level name.
_call_log = _upstream._call_log


async def _fetch(endpoint: str) -> dict:
    """One upstream request. 511 quirks: UTF-8 BOM (decode utf-8-sig),
    plain-text error bodies (never resp.json())."""
    key = os.environ.get("TRANSIT_511_API_KEY", "")
    url = f"{BASE_URL}/{endpoint}?api_key={key}&agency=CT&format=json"
    resp = await _upstream.client().get(url)
    resp.raise_for_status()
    return json.loads(resp.content.decode("utf-8-sig"))


async def get_stop_monitoring() -> tuple[dict, datetime, bool]:
    return await _upstream.get_cached("StopMonitoring", STOP_MONITORING_TTL_S, _fetch)


async def get_service_alerts() -> tuple[dict, datetime, bool]:
    return await _upstream.get_cached("servicealerts", ALERTS_TTL_S, _fetch)


def upstream_calls_last_hour() -> int:
    return _upstream.calls_last_hour()


def cache_status() -> dict:
    """Cache ages for /api/health. Never triggers upstream calls."""
    return _upstream.cache_status({"stop_monitoring": "StopMonitoring", "alerts": "servicealerts"})


def reset() -> None:
    """Clear all module state (tests only)."""
    _upstream.reset()
