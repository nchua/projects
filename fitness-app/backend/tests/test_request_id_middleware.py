"""
Tests for the request-ID middleware.

Covers:
- A generated UUID is attached when no X-Request-ID header is sent.
- The client-provided ID is echoed back when supplied.
- The header is present on error responses (e.g. 404).
- Malformed/overlong client IDs are replaced, not echoed.
"""
import re

import pytest

UUID_HEX_RE = re.compile(r"^[0-9a-f]{32}$")


class TestRequestIdMiddleware:
    def test_generates_id_when_absent(self, client):
        """No inbound X-Request-ID -> a fresh hex UUID appears on the response."""
        response = client.get("/health")
        assert response.status_code == 200
        request_id = response.headers.get("x-request-id") or response.headers.get("X-Request-ID")
        assert request_id is not None, "X-Request-ID header missing from response"
        assert UUID_HEX_RE.match(request_id), f"Expected 32-char hex id, got {request_id!r}"

    def test_echoes_client_supplied_id(self, client):
        """Inbound X-Request-ID is echoed verbatim so clients can correlate."""
        supplied = "client-trace-abc-123"
        response = client.get("/health", headers={"X-Request-ID": supplied})
        assert response.status_code == 200
        assert response.headers.get("x-request-id") == supplied

    def test_header_present_on_error_response(self, client):
        """Middleware still runs for 4xx responses."""
        response = client.get("/definitely-not-a-real-route")
        assert response.status_code == 404
        request_id = response.headers.get("x-request-id")
        assert request_id is not None
        assert UUID_HEX_RE.match(request_id), f"Expected 32-char hex id, got {request_id!r}"

    @pytest.mark.parametrize("injected", [
        "evil id!{injection}",  # chars outside the [A-Za-z0-9._-] whitelist
        "x" * 65,               # one past the 64-char length cap
    ])
    def test_malformed_or_overlong_id_is_replaced(self, client, injected):
        """IDs failing the whitelist are discarded and replaced with a fresh
        UUID — never echoed back (log-injection / trace-spam defense)."""
        response = client.get("/health", headers={"X-Request-ID": injected})
        assert response.status_code == 200
        request_id = response.headers.get("x-request-id")
        assert request_id != injected, "Middleware echoed a non-whitelisted request ID"
        assert UUID_HEX_RE.match(request_id), f"Expected fresh 32-char hex id, got {request_id!r}"

    def test_distinct_ids_across_requests(self, client):
        """Each request without a supplied ID gets its own fresh UUID."""
        r1 = client.get("/health")
        r2 = client.get("/health")
        id1 = r1.headers.get("x-request-id")
        id2 = r2.headers.get("x-request-id")
        assert id1 and id2 and id1 != id2
