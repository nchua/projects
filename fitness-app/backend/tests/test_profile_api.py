"""
Integration tests for Profile API endpoints.

Endpoints tested:
- GET /profile - Fetch current user's profile (defaults for a fresh user)
- PUT /profile - Full and partial updates

Ported from the manual script fitness-app/test-profile.js into pytest.

Schema notes (app/schemas/profile.py):
- ``sex`` must match ``^[MF]$`` (not "male"/"female")
- the weight field is ``bodyweight_lb`` (not "bodyweight")

These tests hit the real FastAPI endpoints via TestClient and the SQLite
test DB from conftest.py.
"""

FULL_UPDATE_PAYLOAD = {
    "age": 30,
    "sex": "M",
    "bodyweight_lb": 180.5,
    "height_inches": 70.0,
    "training_experience": "intermediate",
    "preferred_unit": "lb",
    "e1rm_formula": "epley",
}


class TestGetProfile:
    """GET /profile."""

    def test_fresh_user_gets_default_profile(self, client, auth_headers, unique_email):
        email = unique_email("profile")
        headers, user = auth_headers(email=email)

        resp = client.get("/profile", headers=headers)

        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert body["user_id"] == user.id
        assert body["email"] == email
        # Body metrics start unset.
        assert body["age"] is None
        assert body["sex"] is None
        assert body["bodyweight_lb"] is None
        assert body["height_inches"] is None
        # Training settings fall back to model defaults.
        assert body["training_experience"] == "beginner"
        assert body["preferred_unit"] == "lb"
        assert body["e1rm_formula"] == "epley"
        assert body["created_at"]
        assert body["updated_at"]


class TestUpdateProfile:
    """PUT /profile."""

    def test_full_update_round_trips(self, client, auth_headers, unique_email):
        headers, _user = auth_headers(email=unique_email("profile"))

        resp = client.put("/profile", json=FULL_UPDATE_PAYLOAD, headers=headers)

        assert resp.status_code == 200, resp.json()
        body = resp.json()
        for field, value in FULL_UPDATE_PAYLOAD.items():
            assert body[field] == value, f"{field}: {body[field]} != {value}"

        # A subsequent GET returns the same values (round-trip).
        get_resp = client.get("/profile", headers=headers)
        assert get_resp.status_code == 200
        get_body = get_resp.json()
        for field, value in FULL_UPDATE_PAYLOAD.items():
            assert get_body[field] == value, f"{field}: {get_body[field]} != {value}"

    def test_partial_update_preserves_other_fields(self, client, auth_headers, unique_email):
        headers, _user = auth_headers(email=unique_email("profile"))
        resp = client.put("/profile", json=FULL_UPDATE_PAYLOAD, headers=headers)
        assert resp.status_code == 200, resp.json()

        # Only send age + bodyweight_lb.
        resp = client.put(
            "/profile",
            json={"age": 31, "bodyweight_lb": 185.0},
            headers=headers,
        )

        assert resp.status_code == 200, resp.json()
        body = resp.json()
        # Sent fields changed.
        assert body["age"] == 31
        assert body["bodyweight_lb"] == 185.0
        # Unsent fields preserved from the earlier full update.
        assert body["sex"] == "M"
        assert body["height_inches"] == 70.0
        assert body["training_experience"] == "intermediate"
        assert body["preferred_unit"] == "lb"
        assert body["e1rm_formula"] == "epley"

    def test_sex_must_be_single_letter_m_or_f(self, client, auth_headers, unique_email):
        """The schema pattern is ^[MF]$ — 'male' must be rejected at the schema layer."""
        headers, _user = auth_headers(email=unique_email("profile"))

        resp = client.put("/profile", json={"sex": "male"}, headers=headers)

        assert resp.status_code == 422


class TestProfileAuth:
    """Authentication requirements on /profile."""

    def test_missing_token_rejected(self, client):
        # FastAPI's default HTTPBearer returns 403 when the Authorization
        # header is missing entirely (not 401) — same convention pinned in
        # test_auth_hardening.py. Unauthenticated callers cannot reach it.
        resp = client.get("/profile")
        assert resp.status_code == 403

    def test_garbage_token_rejected(self, client):
        resp = client.get(
            "/profile",
            headers={"Authorization": "Bearer invalid_token_12345"},
        )
        assert resp.status_code == 401

    def test_put_missing_token_rejected(self, client):
        resp = client.put("/profile", json={"age": 30})
        assert resp.status_code == 403
