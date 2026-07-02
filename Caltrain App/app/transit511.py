"""511.org upstream client.

Everything here exists to respect the 60 requests / rolling hour key limit:
lazy fetches only, per-endpoint TTL cache, a stampede lock, a rolling-hour
call guard, and serve-last-good-as-stale on any failure.

Cache and lock identities are logical endpoint names — the keyed URL (which
carries the API key) exists only inside _fetch, so the secret never appears
in cache keys, lock keys, or exception messages.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

BASE_URL = "https://api.511.org/transit"

STOP_MONITORING_TTL_S = 60
ALERTS_TTL_S = 300
RATE_GUARD_MAX_CALLS_PER_HOUR = 55
UPSTREAM_TIMEOUT_S = 10


class UpstreamNeverFetchedError(RuntimeError):
    """511 is unreachable and we have no cached payload to fall back on."""


@dataclass
class _CacheEntry:
    payload: dict
    fetched_at: datetime


_cache: dict[str, _CacheEntry] = {}
_locks: dict[str, asyncio.Lock] = {}
_call_log: deque[datetime] = deque()
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """Shared client: connection keep-alive avoids a fresh TCP+TLS handshake
    on every cache-miss fetch (which lands on a user-facing request)."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT_S)
    return _client


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _prune_call_log() -> None:
    cutoff = _now()
    while _call_log and (cutoff - _call_log[0]).total_seconds() > 3600:
        _call_log.popleft()


def upstream_calls_last_hour() -> int:
    _prune_call_log()
    return len(_call_log)


def _rate_guard_allows_call() -> bool:
    return upstream_calls_last_hour() < RATE_GUARD_MAX_CALLS_PER_HOUR


async def _fetch(endpoint: str) -> dict:
    """One upstream request. 511 quirks: UTF-8 BOM (decode utf-8-sig),
    plain-text error bodies (never resp.json())."""
    key = os.environ.get("TRANSIT_511_API_KEY", "")
    url = f"{BASE_URL}/{endpoint}?api_key={key}&agency=CT&format=json"
    resp = await _get_client().get(url)
    resp.raise_for_status()
    return json.loads(resp.content.decode("utf-8-sig"))


async def _get_cached(endpoint: str, ttl_s: int) -> tuple[dict, datetime, bool]:
    """Return (payload, fetched_at, stale). Fetches at most once per TTL
    window regardless of concurrent callers; on failure serves last-good."""
    entry = _cache.get(endpoint)
    if entry and (_now() - entry.fetched_at).total_seconds() < ttl_s:
        return entry.payload, entry.fetched_at, False

    lock = _locks.setdefault(endpoint, asyncio.Lock())
    async with lock:
        entry = _cache.get(endpoint)  # re-check: another caller may have fetched
        if entry and (_now() - entry.fetched_at).total_seconds() < ttl_s:
            return entry.payload, entry.fetched_at, False

        if _rate_guard_allows_call():
            _call_log.append(_now())  # count attempts, not successes
            try:
                payload = await _fetch(endpoint)
            except (httpx.HTTPError, ValueError):
                pass  # fall through to stale / never-fetched
            else:
                entry = _CacheEntry(payload, _now())
                _cache[endpoint] = entry
                return entry.payload, entry.fetched_at, False

        if entry:
            return entry.payload, entry.fetched_at, True
        raise UpstreamNeverFetchedError(endpoint)


async def get_stop_monitoring() -> tuple[dict, datetime, bool]:
    return await _get_cached("StopMonitoring", STOP_MONITORING_TTL_S)


async def get_service_alerts() -> tuple[dict, datetime, bool]:
    return await _get_cached("servicealerts", ALERTS_TTL_S)


def cache_status() -> dict:
    """Cache ages for /api/health. Never triggers upstream calls."""
    now = _now()
    status = {}
    for name, endpoint in (("stop_monitoring", "StopMonitoring"), ("alerts", "servicealerts")):
        entry = _cache.get(endpoint)
        status[name] = {
            "age_seconds": int((now - entry.fetched_at).total_seconds()) if entry else None,
            "have_data": entry is not None,
        }
    return status


def reset() -> None:
    """Clear all module state (tests only)."""
    global _client
    _cache.clear()
    _locks.clear()
    _call_log.clear()
    _client = None
