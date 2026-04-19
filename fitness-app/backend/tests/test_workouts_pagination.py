"""
Tests for GET /workouts pagination.

Verifies:
- Default limit (50) is applied when no limit is passed.
- Custom limit/offset slices the result list correctly.
- Validation caps limit at 200.
"""
from datetime import datetime, timedelta, timezone

from app.models.workout import WorkoutSession


def _seed_workouts(db, user_id: str, count: int) -> None:
    """Create `count` workouts with descending dates so ordering is stable."""
    now = datetime.now(timezone.utc)
    for i in range(count):
        db.add(WorkoutSession(
            user_id=user_id,
            date=now - timedelta(days=i),
            duration_minutes=60,
        ))
    db.commit()


class TestWorkoutsPagination:
    def test_default_limit_is_50(self, client, db, auth_headers):
        headers, user = auth_headers()
        _seed_workouts(db, user.id, 60)

        resp = client.get("/workouts", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # New default is 50 (was 20 before PR E).
        assert len(data) == 50

    def test_custom_limit(self, client, db, auth_headers):
        headers, user = auth_headers()
        _seed_workouts(db, user.id, 60)

        resp = client.get("/workouts?limit=10", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 10

    def test_offset_skips_earlier_pages(self, client, db, auth_headers):
        headers, user = auth_headers()
        _seed_workouts(db, user.id, 60)

        page1 = client.get("/workouts?limit=10&offset=0", headers=headers).json()
        page2 = client.get("/workouts?limit=10&offset=10", headers=headers).json()

        assert len(page1) == 10
        assert len(page2) == 10
        page1_ids = {w["id"] for w in page1}
        page2_ids = {w["id"] for w in page2}
        assert page1_ids.isdisjoint(page2_ids)

    def test_limit_capped_at_200(self, client, auth_headers):
        """limit > 200 should be rejected by FastAPI validation (422)."""
        headers, _ = auth_headers()
        resp = client.get("/workouts?limit=201", headers=headers)
        assert resp.status_code == 422

    def test_limit_200_allowed(self, client, db, auth_headers):
        """limit=200 is the explicit max and should be accepted."""
        headers, user = auth_headers()
        _seed_workouts(db, user.id, 60)

        resp = client.get("/workouts?limit=200", headers=headers)
        assert resp.status_code == 200
        # Only 60 workouts exist, so we get them all back.
        assert len(resp.json()) == 60
