"""Test backend idempotency via client_id on POST /workouts.

Scenario we're protecting against: iOS offline queue enqueues a WorkoutCreate
with client_id=X. On retry, the server received the original request but the
client timed out, so the queue retries. Without dedupe, the second POST
creates a duplicate workout. With dedupe, the second POST returns the same
workout the first call created.
"""
import pytest


def _sample_workout(client_id: str, exercise_id: str) -> dict:
    return {
        "date": "2026-04-19",
        "duration_minutes": 45,
        "client_id": client_id,
        "exercises": [
            {
                "exercise_id": exercise_id,
                "order_index": 0,
                "sets": [
                    {"weight": 135, "weight_unit": "lb", "reps": 5, "set_number": 1}
                ],
            }
        ],
    }


@pytest.fixture
def seeded_exercise(db):
    """Insert one seeded exercise row and return its id."""
    from app.models.exercise import Exercise
    ex = Exercise(name="Bench Press", is_custom=False, category="Push")
    db.add(ex)
    db.commit()
    return ex.id


class TestClientIdDedupe:
    def test_first_post_creates_workout(self, client, auth_headers, seeded_exercise):
        headers, _ = auth_headers()
        body = _sample_workout("dedupe-test-1", seeded_exercise)
        r = client.post("/workouts", json=body, headers=headers)
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["workout"]["id"]
        # First save: full celebration payload may be present.
        assert data["xp_earned"] >= 0

    def test_retry_with_same_client_id_returns_existing(
        self, client, auth_headers, seeded_exercise
    ):
        """Second POST with the same client_id must return the ORIGINAL workout
        without creating a new row or re-awarding XP.
        """
        headers, _ = auth_headers()
        body = _sample_workout("dedupe-test-2", seeded_exercise)

        first = client.post("/workouts", json=body, headers=headers)
        assert first.status_code == 201, first.text
        first_id = first.json()["workout"]["id"]

        second = client.post("/workouts", json=body, headers=headers)
        # Still 201 because FastAPI's decorator sets it; the BODY is what matters.
        assert second.status_code in (200, 201), second.text
        assert second.json()["workout"]["id"] == first_id
        # Dedupe path emits an empty celebration payload — no double-awards.
        assert second.json()["xp_earned"] == 0
        assert second.json()["achievements_unlocked"] == []
        assert second.json()["prs_achieved"] == []

    def test_different_users_dont_collide(
        self, client, auth_headers, seeded_exercise
    ):
        """Same client_id from different users must create independent workouts
        (uniqueness is scoped to (user_id, client_id)).
        """
        # First user saves.
        headers1, _ = auth_headers(email="hunter@example.com", password="TestPass123!")
        body1 = _sample_workout("shared-client-id", seeded_exercise)
        r1 = client.post("/workouts", json=body1, headers=headers1)
        assert r1.status_code == 201
        first_id = r1.json()["workout"]["id"]

        # Second user saves with the same client_id.
        headers2, _ = auth_headers(email="other@example.com", password="TestPass123!")
        body2 = _sample_workout("shared-client-id", seeded_exercise)
        r2 = client.post("/workouts", json=body2, headers=headers2)
        assert r2.status_code == 201
        second_id = r2.json()["workout"]["id"]

        assert first_id != second_id

    def test_omitted_client_id_always_creates(
        self, client, auth_headers, seeded_exercise
    ):
        """Web clients that don't send client_id must NOT be dedupe-blocked."""
        headers, _ = auth_headers()
        body = _sample_workout("", seeded_exercise)  # replaced below
        body.pop("client_id")

        r1 = client.post("/workouts", json=body, headers=headers)
        r2 = client.post("/workouts", json=body, headers=headers)
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["workout"]["id"] != r2.json()["workout"]["id"]
