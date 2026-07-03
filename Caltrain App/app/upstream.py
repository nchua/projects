"""Generic upstream client machinery, shared by every transit feed.

Extracted from transit511.py (SPEC-BART §6.1): per-endpoint TTL cache, a
stampede lock, a rolling-hour call guard, and serve-last-good-as-stale on any
failure. Each upstream (511, BART) constructs its own Upstream instance, so
call logs and guards never mix — a BART fetch can never spend 511 quota.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx


class UpstreamNeverFetchedError(RuntimeError):
    """Upstream is unreachable and we have no cached payload to fall back on."""


@dataclass
class _CacheEntry:
    payload: object
    fetched_at: datetime


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Upstream:
    """One upstream feed's cache + politeness state.

    fetch is called with the endpoint name and must return the payload to
    cache (already decoded/parsed — parse errors should raise ValueError so
    they count as fetch failures and stale data is served instead).
    """

    guard_max_calls_per_hour: int
    timeout_s: int
    # BART's endpoints 301/307-redirect and need this; 511 keeps its original
    # behavior (a redirect is a fetch failure → serve stale)
    follow_redirects: bool = False
    _cache: dict[str, _CacheEntry] = field(default_factory=dict)
    _locks: dict[str, asyncio.Lock] = field(default_factory=dict)
    _call_log: deque[datetime] = field(default_factory=deque)
    _client: httpx.AsyncClient | None = None

    def client(self) -> httpx.AsyncClient:
        """Shared client: connection keep-alive avoids a fresh TCP+TLS
        handshake on every cache-miss fetch (which lands on a user-facing
        request)."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout_s, follow_redirects=self.follow_redirects
            )
        return self._client

    def _prune_call_log(self) -> None:
        cutoff = _now()
        while self._call_log and (cutoff - self._call_log[0]).total_seconds() > 3600:
            self._call_log.popleft()

    def calls_last_hour(self) -> int:
        self._prune_call_log()
        return len(self._call_log)

    def _guard_allows_call(self) -> bool:
        return self.calls_last_hour() < self.guard_max_calls_per_hour

    async def get_cached(
        self,
        endpoint: str,
        ttl_s: int,
        fetch: Callable[[str], Awaitable[object]],
    ) -> tuple[object, datetime, bool]:
        """Return (payload, fetched_at, stale). Fetches at most once per TTL
        window regardless of concurrent callers; on failure serves last-good."""
        entry = self._cache.get(endpoint)
        if entry and (_now() - entry.fetched_at).total_seconds() < ttl_s:
            return entry.payload, entry.fetched_at, False

        lock = self._locks.setdefault(endpoint, asyncio.Lock())
        async with lock:
            entry = self._cache.get(endpoint)  # re-check: another caller may have fetched
            if entry and (_now() - entry.fetched_at).total_seconds() < ttl_s:
                return entry.payload, entry.fetched_at, False

            if self._guard_allows_call():
                self._call_log.append(_now())  # count attempts, not successes
                try:
                    payload = await fetch(endpoint)
                except (httpx.HTTPError, ValueError):
                    pass  # fall through to stale / never-fetched
                else:
                    entry = _CacheEntry(payload, _now())
                    self._cache[endpoint] = entry
                    return entry.payload, entry.fetched_at, False

            if entry:
                return entry.payload, entry.fetched_at, True
            raise UpstreamNeverFetchedError(endpoint)

    def cache_status(self, names: dict[str, str]) -> dict:
        """Cache ages for /api/health, keyed by display name. Never fetches."""
        now = _now()
        status = {}
        for name, endpoint in names.items():
            entry = self._cache.get(endpoint)
            status[name] = {
                "age_seconds": int((now - entry.fetched_at).total_seconds()) if entry else None,
                "have_data": entry is not None,
            }
        return status

    def reset(self) -> None:
        """Clear all state (tests only)."""
        self._cache.clear()
        self._locks.clear()
        self._call_log.clear()
        self._client = None
