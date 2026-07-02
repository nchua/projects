"""
Integration tests for Bodyweight API endpoints.

Endpoints tested:
- POST /bodyweight - Log entry (upsert per user+date)
- GET /bodyweight - History with rolling averages + trend analytics
- GET /bodyweight/{id} - Fetch single entry
- DELETE /bodyweight/{id} - Delete entry

Ported from the manual script fitness-app/test-bodyweight.js into pytest.

Behavior notes (app/api/bodyweight.py):
- Weight is always stored in lb; kg input is converted with KG_TO_LB=2.20462.
- POST is an upsert on (user, date) and always returns 201.
- History analytics need >=3 entries in the last 7 days for the 7-day
  rolling average and >=7 entries in the last 14 days for a trend.
"""
from datetime import date, timedelta

import pytest

KG_TO_LB = 2.20462


def _entry_payload(day: date = None, weight: float = 165.5, unit: str = "lb", source: str = "manual") -> dict:
    return {
        "date": (day or date.today()).isoformat(),
        "weight": weight,
        "weight_unit": unit,
        "source": source,
    }


class TestLogBodyweight:
    """POST /bodyweight."""

    def test_create_entry_response_contract(self, client, auth_headers, unique_email):
        headers, user = auth_headers(email=unique_email("bw"))

        resp = client.post("/bodyweight", json=_entry_payload(weight=165.5), headers=headers)

        assert resp.status_code == 201, resp.json()
        body = resp.json()
        assert body["id"]
        assert body["user_id"] == user.id
        assert body["date"].startswith(date.today().isoformat())
        assert body["weight_lb"] == 165.5
        # Display unit follows the profile's preferred unit (default lb).
        assert body["weight_display"] == 165.5
        assert body["weight_unit"] == "lb"
        assert body["source"] == "manual"
        assert body["created_at"]
        assert body["updated_at"]

    def test_same_date_upserts_instead_of_duplicating(self, client, auth_headers, unique_email):
        headers, _user = auth_headers(email=unique_email("bw"))
        first = client.post("/bodyweight", json=_entry_payload(weight=165.5), headers=headers)
        assert first.status_code == 201

        resp = client.post("/bodyweight", json=_entry_payload(weight=164.0), headers=headers)

        # Upsert: still 201, same row updated in place.
        assert resp.status_code == 201, resp.json()
        assert resp.json()["id"] == first.json()["id"]
        assert resp.json()["weight_lb"] == 164.0

        history = client.get("/bodyweight", headers=headers)
        assert history.status_code == 200
        assert history.json()["total_entries"] == 1

    def test_kg_entry_converted_to_lb_for_storage(self, client, auth_headers, unique_email):
        headers, _user = auth_headers(email=unique_email("bw"))

        resp = client.post("/bodyweight", json=_entry_payload(weight=75.0, unit="kg"), headers=headers)

        assert resp.status_code == 201, resp.json()
        body = resp.json()
        # 75 kg * 2.20462 = 165.35 lb (rounded to 2 decimals in the response).
        assert body["weight_lb"] == pytest.approx(75.0 * KG_TO_LB, abs=0.01)
        # Display falls back to the preferred unit (lb by default).
        assert body["weight_display"] == pytest.approx(75.0 * KG_TO_LB, abs=0.01)
        assert body["weight_unit"] == "lb"


class TestBodyweightHistory:
    """GET /bodyweight — history + analytics."""

    def test_history_returns_rolling_average_and_trend(self, client, auth_headers, unique_email):
        headers, _user = auth_headers(email=unique_email("bw"))
        today = date.today()

        # Seed 8 daily entries trending upward: 173 lb (7 days ago) -> 180 lb (today).
        for days_ago in range(8):
            resp = client.post(
                "/bodyweight",
                json=_entry_payload(day=today - timedelta(days=days_ago), weight=180.0 - days_ago),
                headers=headers,
            )
            assert resp.status_code == 201, resp.json()

        resp = client.get("/bodyweight", headers=headers)

        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert body["total_entries"] == 8
        assert len(body["entries"]) == 8
        # Entries ordered by date descending (today first).
        assert body["entries"][0]["weight_lb"] == 180.0
        assert body["entries"][-1]["weight_lb"] == 173.0

        # All 8 entries fall inside the (inclusive) 7-day window: mean = 176.5.
        assert body["rolling_average_7day"] == pytest.approx(176.5, abs=0.01)
        assert body["rolling_average_14day"] == pytest.approx(176.5, abs=0.01)

        # First-half avg 174.5 vs second-half avg 178.5 -> gaining at 4 lb/week.
        assert body["trend"] == "gaining"
        assert body["trend_rate_per_week"] == pytest.approx(4.0, abs=0.01)
        assert body["is_plateau"] is False
        assert body["min_weight"] == 173.0
        assert body["max_weight"] == 180.0

    def test_history_insufficient_data_for_analytics(self, client, auth_headers, unique_email):
        headers, _user = auth_headers(email=unique_email("bw"))
        resp = client.post("/bodyweight", json=_entry_payload(weight=170.0), headers=headers)
        assert resp.status_code == 201

        resp = client.get("/bodyweight", headers=headers)

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_entries"] == 1
        assert body["rolling_average_7day"] is None
        assert body["trend"] == "insufficient_data"
        assert body["trend_rate_per_week"] is None


class TestBodyweightEntryDetail:
    """GET /bodyweight/{id} and DELETE /bodyweight/{id}."""

    def test_get_then_delete_then_404(self, client, auth_headers, unique_email):
        headers, _user = auth_headers(email=unique_email("bw"))
        created = client.post("/bodyweight", json=_entry_payload(weight=165.5), headers=headers)
        assert created.status_code == 201
        entry_id = created.json()["id"]

        get_resp = client.get(f"/bodyweight/{entry_id}", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == entry_id
        assert get_resp.json()["weight_lb"] == 165.5

        delete_resp = client.delete(f"/bodyweight/{entry_id}", headers=headers)
        assert delete_resp.status_code == 204

        gone_resp = client.get(f"/bodyweight/{entry_id}", headers=headers)
        assert gone_resp.status_code == 404

        # History no longer includes the deleted entry.
        history = client.get("/bodyweight", headers=headers)
        assert history.json()["total_entries"] == 0

    def test_get_nonexistent_entry_404(self, client, auth_headers, unique_email):
        headers, _user = auth_headers(email=unique_email("bw"))
        resp = client.get("/bodyweight/nonexistent-id", headers=headers)
        assert resp.status_code == 404


class TestBodyweightAuth:
    """Authentication requirements on /bodyweight."""

    def test_missing_token_rejected(self, client):
        # FastAPI's default HTTPBearer returns 403 when the Authorization
        # header is missing entirely (not 401) — same convention pinned in
        # test_auth_hardening.py. Unauthenticated callers cannot reach it.
        resp = client.get("/bodyweight")
        assert resp.status_code == 403

    def test_garbage_token_rejected(self, client):
        resp = client.get(
            "/bodyweight",
            headers={"Authorization": "Bearer invalid_token_12345"},
        )
        assert resp.status_code == 401

    def test_post_missing_token_rejected(self, client):
        resp = client.post("/bodyweight", json=_entry_payload())
        assert resp.status_code == 403
