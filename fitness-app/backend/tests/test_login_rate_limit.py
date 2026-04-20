"""
Tests for login brute-force protection.

The /auth/login endpoint is limited to 5 attempts per 10 minutes per client
IP. These tests verify the 6th attempt within the window gets a 429 with a
Retry-After header, and that a reset (simulating window expiry) allows new
attempts.
"""


def _bad_login(client, email: str):
    return client.post(
        "/auth/login",
        json={"email": email, "password": "WrongPassword1!"},
    )


class TestLoginRateLimit:
    def test_sixth_failed_login_returns_429(self, client, create_test_user):
        """5 failures pass through as 401, 6th is blocked with 429."""
        create_test_user(email="ratelimited@example.com", password="TestPass123!")

        # First 5 attempts should all be processed by the endpoint and
        # return 401 (wrong password), not 429.
        for i in range(5):
            response = _bad_login(client, "ratelimited@example.com")
            assert response.status_code == 401, (
                f"Attempt {i + 1} should be 401 (wrong password), got {response.status_code}"
            )

        # 6th attempt within the window -> rate-limited.
        response = _bad_login(client, "ratelimited@example.com")
        assert response.status_code == 429
        body = response.json()
        assert "detail" in body
        # Retry-After must be present and positive.
        retry_after = response.headers.get("retry-after") or response.headers.get("Retry-After")
        assert retry_after is not None, "Retry-After header missing on 429"
        assert int(retry_after) > 0

    def test_rate_limit_blocks_even_valid_credentials(self, client, create_test_user):
        """After hitting the limit, even correct credentials are blocked until reset."""
        create_test_user(email="lockedout@example.com", password="TestPass123!")

        # Exhaust the window with bad attempts.
        for _ in range(5):
            _bad_login(client, "lockedout@example.com")

        # Even a correct login is rate-limited.
        response = client.post(
            "/auth/login",
            json={"email": "lockedout@example.com", "password": "TestPass123!"},
        )
        assert response.status_code == 429

    def test_rate_limit_resets_after_window(self, client, create_test_user):
        """Simulating window expiry (via limiter.reset) allows new attempts."""
        from main import app as _app

        create_test_user(email="resets@example.com", password="TestPass123!")

        # Exhaust the limit.
        for _ in range(5):
            _bad_login(client, "resets@example.com")
        blocked = _bad_login(client, "resets@example.com")
        assert blocked.status_code == 429

        # Simulate window expiry by resetting the limiter state.
        # (In production the memory-backed limiter rolls over naturally
        # after the window elapses.)
        _app.state.limiter.reset()

        # Now a valid login should succeed again.
        response = client.post(
            "/auth/login",
            json={"email": "resets@example.com", "password": "TestPass123!"},
        )
        assert response.status_code == 200, (
            f"Expected 200 after reset, got {response.status_code}: {response.json()}"
        )

    def test_register_has_looser_rate_limit(self, client):
        """POST /auth/register permits higher burst than /auth/login — shared-NAT
        networks (gyms, coffee shops) must be able to sign up multiple users in
        one 10-minute window. Policy is 20/10min vs login's 5/10min.
        """
        # First 20 registrations with different emails -> 201 each.
        for i in range(20):
            response = client.post(
                "/auth/register",
                json={"email": f"reg{i}@example.com", "password": "StrongPass1!"},
            )
            assert response.status_code == 201, (
                f"Attempt {i + 1} expected 201, got {response.status_code}"
            )

        # 21st -> blocked.
        response = client.post(
            "/auth/register",
            json={"email": "reg21@example.com", "password": "StrongPass1!"},
        )
        assert response.status_code == 429

    def test_proxy_forwarded_header_distinguishes_clients(self, client, create_test_user):
        """X-Forwarded-For is the true client IP on Railway; two different
        clients behind the same proxy must not share each other's quota.
        """
        create_test_user(email="proxytest@example.com", password="TestPass123!")

        # Client A burns through 5 attempts.
        for _ in range(5):
            response = client.post(
                "/auth/login",
                json={"email": "proxytest@example.com", "password": "WrongPass1!"},
                headers={"X-Forwarded-For": "203.0.113.10"},
            )
            assert response.status_code == 401

        # 6th attempt from A is blocked.
        blocked = client.post(
            "/auth/login",
            json={"email": "proxytest@example.com", "password": "WrongPass1!"},
            headers={"X-Forwarded-For": "203.0.113.10"},
        )
        assert blocked.status_code == 429

        # Different client behind the same proxy — fresh quota.
        fresh = client.post(
            "/auth/login",
            json={"email": "proxytest@example.com", "password": "TestPass123!"},
            headers={"X-Forwarded-For": "198.51.100.77"},
        )
        assert fresh.status_code == 200, (
            f"Expected 200 from a different X-Forwarded-For IP, got {fresh.status_code}"
        )
