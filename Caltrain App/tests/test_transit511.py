"""Upstream client: BOM decoding, TTL cache, stale fallback, rate guard."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx
from app import transit511
from conftest import bom_bytes as _bom_payload

SM_URL = f"{transit511.BASE_URL}/StopMonitoring"


@respx.mock
async def test_decodes_bom_prefixed_fixture_bytes(stopmonitoring_bytes):
    respx.get(url__startswith=SM_URL).mock(return_value=httpx.Response(200, content=stopmonitoring_bytes))
    payload, fetched_at, stale = await transit511.get_stop_monitoring()
    assert stale is False
    assert "ServiceDelivery" in payload
    assert fetched_at.tzinfo is not None


@respx.mock
async def test_second_call_within_ttl_hits_cache():
    route = respx.get(url__startswith=SM_URL).mock(
        return_value=httpx.Response(200, content=_bom_payload({"ServiceDelivery": {}}))
    )
    await transit511.get_stop_monitoring()
    await transit511.get_stop_monitoring()
    assert route.call_count == 1
    assert transit511.upstream_calls_last_hour() == 1


@respx.mock
async def test_upstream_failure_serves_last_good_as_stale(monkeypatch):
    monkeypatch.setattr(transit511, "STOP_MONITORING_TTL_S", 0)
    route = respx.get(url__startswith=SM_URL)
    route.side_effect = [
        httpx.Response(200, content=_bom_payload({"ServiceDelivery": {"marker": 1}})),
        httpx.Response(500, content=b"Internal Server Error"),
    ]
    payload1, _, stale1 = await transit511.get_stop_monitoring()
    payload2, _, stale2 = await transit511.get_stop_monitoring()
    assert stale1 is False
    assert stale2 is True
    assert payload2 == payload1


@respx.mock
async def test_failure_with_cold_cache_raises():
    respx.get(url__startswith=SM_URL).mock(return_value=httpx.Response(500, content=b"nope"))
    with pytest.raises(transit511.UpstreamNeverFetchedError):
        await transit511.get_stop_monitoring()


@respx.mock
async def test_plain_text_error_body_never_json_parsed():
    # 511 error bodies are plain text (e.g. 401) — must not blow up parsing.
    respx.get(url__startswith=SM_URL).mock(
        return_value=httpx.Response(401, content=b"The API key is not provided.")
    )
    with pytest.raises(transit511.UpstreamNeverFetchedError):
        await transit511.get_stop_monitoring()


@respx.mock
async def test_rate_guard_blocks_upstream_and_serves_stale(monkeypatch):
    route = respx.get(url__startswith=SM_URL).mock(
        return_value=httpx.Response(200, content=_bom_payload({"ServiceDelivery": {}}))
    )
    payload1, _, _ = await transit511.get_stop_monitoring()

    monkeypatch.setattr(transit511, "STOP_MONITORING_TTL_S", 0)  # expire the cache
    transit511._call_log.extend(
        [datetime.now(timezone.utc)] * transit511.RATE_GUARD_MAX_CALLS_PER_HOUR
    )

    payload2, _, stale = await transit511.get_stop_monitoring()
    assert route.call_count == 1  # guard prevented the second request
    assert stale is True
    assert payload2 == payload1


@respx.mock
async def test_rate_guard_with_no_cache_raises_without_calling():
    route = respx.get(url__startswith=SM_URL)
    transit511._call_log.extend(
        [datetime.now(timezone.utc)] * transit511.RATE_GUARD_MAX_CALLS_PER_HOUR
    )
    with pytest.raises(transit511.UpstreamNeverFetchedError):
        await transit511.get_stop_monitoring()
    assert route.call_count == 0


def test_call_log_prunes_entries_older_than_an_hour():
    old = datetime.now(timezone.utc) - timedelta(seconds=3700)
    transit511._call_log.append(old)
    transit511._call_log.append(datetime.now(timezone.utc))
    assert transit511.upstream_calls_last_hour() == 1
