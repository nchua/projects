"""BART upstream caching: TTL, stale-serving, politeness guard, redirects —
mirrors the 511 tests over the shared app.upstream machinery."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx
from app import bart
from app.upstream import UpstreamNeverFetchedError

TU_URL = "https://api.bart.gov/gtfsrt/tripupdate.aspx"

pytestmark = pytest.mark.asyncio


def _age_cache_entry(endpoint: str, seconds: int) -> None:
    entry = bart._upstream._cache[endpoint]
    entry.fetched_at -= timedelta(seconds=seconds)


@respx.mock
async def test_ttl_cache_fetches_once(bart_tripupdate_bytes):
    route = respx.get(TU_URL).mock(return_value=httpx.Response(200, content=bart_tripupdate_bytes))
    first, _, stale_first = await bart.get_trip_updates()
    second, _, stale_second = await bart.get_trip_updates()
    assert route.call_count == 1
    assert first is second
    assert stale_first is stale_second is False
    assert len(first["trips"]) == 85


@respx.mock
async def test_http_redirect_is_followed(bart_tripupdate_bytes):
    # target route first: the paramless matcher would swallow it otherwise
    respx.get(TU_URL, params={"r": "1"}).mock(
        return_value=httpx.Response(200, content=bart_tripupdate_bytes)
    )
    respx.get(TU_URL).mock(
        return_value=httpx.Response(307, headers={"Location": TU_URL + "?r=1"})
    )
    payload, _, stale = await bart.get_trip_updates()
    assert stale is False
    assert payload["trips"]


@respx.mock
async def test_expired_cache_refetches(bart_tripupdate_bytes):
    route = respx.get(TU_URL).mock(return_value=httpx.Response(200, content=bart_tripupdate_bytes))
    await bart.get_trip_updates()
    _age_cache_entry("tripupdate.aspx", bart.TRIP_UPDATES_TTL_S + 1)
    _, _, stale = await bart.get_trip_updates()
    assert route.call_count == 2
    assert stale is False


@respx.mock
async def test_fetch_failure_serves_stale(bart_tripupdate_bytes):
    route = respx.get(TU_URL)
    route.side_effect = [
        httpx.Response(200, content=bart_tripupdate_bytes),
        httpx.Response(500),
    ]
    payload, _, _ = await bart.get_trip_updates()
    _age_cache_entry("tripupdate.aspx", bart.TRIP_UPDATES_TTL_S + 1)
    stale_payload, _, stale = await bart.get_trip_updates()
    assert stale is True
    assert stale_payload is payload


@respx.mock
async def test_undecodable_body_counts_as_failure_and_serves_stale(bart_tripupdate_bytes):
    route = respx.get(TU_URL)
    route.side_effect = [
        httpx.Response(200, content=bart_tripupdate_bytes),
        httpx.Response(200, content=b"not a protobuf at all"),
    ]
    payload, _, _ = await bart.get_trip_updates()
    _age_cache_entry("tripupdate.aspx", bart.TRIP_UPDATES_TTL_S + 1)
    stale_payload, _, stale = await bart.get_trip_updates()
    assert stale is True
    assert stale_payload is payload


@respx.mock
async def test_never_fetched_and_unreachable_raises():
    respx.get(TU_URL).mock(return_value=httpx.Response(500))
    with pytest.raises(UpstreamNeverFetchedError):
        await bart.get_trip_updates()


@respx.mock
async def test_politeness_guard_blocks_calls_and_serves_stale(bart_tripupdate_bytes):
    route = respx.get(TU_URL).mock(return_value=httpx.Response(200, content=bart_tripupdate_bytes))
    await bart.get_trip_updates()
    bart._upstream._call_log.extend(
        [datetime.now(timezone.utc)] * bart.GUARD_MAX_CALLS_PER_HOUR
    )
    _age_cache_entry("tripupdate.aspx", bart.TRIP_UPDATES_TTL_S + 1)
    _, _, stale = await bart.get_trip_updates()
    assert route.call_count == 1  # guard blocked the refetch
    assert stale is True


async def test_call_log_is_independent_of_511():
    from app import transit511

    bart._upstream._call_log.append(datetime.now(timezone.utc))
    assert bart.upstream_calls_last_hour() == 1
    assert transit511.upstream_calls_last_hour() == 0


async def test_cache_status_names():
    status = bart.cache_status()
    assert set(status) == {"bart_trip_updates", "bart_alerts"}
    assert status["bart_trip_updates"] == {"age_seconds": None, "have_data": False}
