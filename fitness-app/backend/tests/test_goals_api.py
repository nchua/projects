"""
Integration tests for Goals API endpoints.

Endpoints tested:
- POST /goals - Create single goal
- POST /goals/batch - Create multiple goals
- GET /goals - List user goals
- GET /goals/{id} - Get goal detail
- PUT /goals/{id} - Update goal
- DELETE /goals/{id} - Abandon goal

Key business rules tested:
- Maximum 5 active goals per user
- Batch creation respects the limit
- Goal progress tracking

These tests hit the real FastAPI endpoints via TestClient and the SQLite
test DB from conftest.py. The previous revision of this file was mostly
pseudo-tests asserting on hand-built mock lists — those have been
converted to real endpoint calls or removed (see TODO markers).
"""
from datetime import date, timedelta

from app.models.exercise import Exercise
from app.services.mission_service import MAX_ACTIVE_GOALS


def _seed_exercise(
    db,
    *,
    id: str = "ex-bench-001",
    name: str = "Barbell Bench Press",
    category: str = "compound",
) -> Exercise:
    """Insert an exercise row into the test DB and return it."""
    exercise = Exercise(id=id, name=name, category=category)
    db.add(exercise)
    db.commit()
    db.refresh(exercise)
    return exercise


def _goal_payload(exercise_id: str, *, target_weight: float = 225, target_reps: int = 1) -> dict:
    return {
        "exercise_id": exercise_id,
        "target_weight": target_weight,
        "target_reps": target_reps,
        "weight_unit": "lb",
        "deadline": (date.today() + timedelta(weeks=12)).isoformat(),
    }


class TestMaxGoalsLimit:
    """Enforces the MAX_ACTIVE_GOALS (5) business rule."""

    def test_single_goal_creation_allowed_when_under_limit(self, client, db, auth_headers):
        headers, _user = auth_headers()
        exercise = _seed_exercise(db)

        resp = client.post("/goals", json=_goal_payload(exercise.id), headers=headers)

        assert resp.status_code == 201, resp.json()
        assert resp.json()["target_weight"] == 225

    def test_single_goal_creation_blocked_at_limit(self, client, db, auth_headers):
        headers, _user = auth_headers()
        # Seed 5 exercises and create 5 goals to hit the cap.
        for i in range(MAX_ACTIVE_GOALS):
            ex = _seed_exercise(db, id=f"ex-cap-{i:03d}", name=f"Exercise {i}")
            resp = client.post("/goals", json=_goal_payload(ex.id), headers=headers)
            assert resp.status_code == 201, resp.json()

        # 6th should fail.
        extra = _seed_exercise(db, id="ex-cap-999", name="Extra Exercise")
        resp = client.post("/goals", json=_goal_payload(extra.id), headers=headers)

        assert resp.status_code == 400
        assert "Maximum" in resp.json()["detail"]


class TestBatchGoalCreation:
    """POST /goals/batch."""

    def test_batch_creation_success_when_under_limit(self, client, db, auth_headers):
        headers, _user = auth_headers()
        ex1 = _seed_exercise(db, id="ex-batch-1", name="Bench")
        ex2 = _seed_exercise(db, id="ex-batch-2", name="Squat")
        ex3 = _seed_exercise(db, id="ex-batch-3", name="Deadlift")

        resp = client.post(
            "/goals/batch",
            json={"goals": [_goal_payload(ex1.id), _goal_payload(ex2.id), _goal_payload(ex3.id)]},
            headers=headers,
        )

        assert resp.status_code == 201, resp.json()
        body = resp.json()
        assert body["created_count"] == 3
        assert body["active_count"] == 3

    def test_batch_creation_blocked_when_would_exceed_limit(self, client, db, auth_headers):
        headers, _user = auth_headers()
        # Pre-seed 4 goals.
        for i in range(4):
            ex = _seed_exercise(db, id=f"ex-pre-{i}", name=f"Pre {i}")
            resp = client.post("/goals", json=_goal_payload(ex.id), headers=headers)
            assert resp.status_code == 201

        # Batch of 2 more would exceed limit of 5.
        ex_a = _seed_exercise(db, id="ex-batch-a", name="A")
        ex_b = _seed_exercise(db, id="ex-batch-b", name="B")
        resp = client.post(
            "/goals/batch",
            json={"goals": [_goal_payload(ex_a.id), _goal_payload(ex_b.id)]},
            headers=headers,
        )

        assert resp.status_code == 400
        assert "Can only create" in resp.json()["detail"]

    def test_batch_size_cannot_exceed_max(self, client, db, auth_headers):
        headers, _user = auth_headers()
        exercises = [
            _seed_exercise(db, id=f"ex-big-{i}", name=f"Big {i}")
            for i in range(MAX_ACTIVE_GOALS + 1)
        ]

        resp = client.post(
            "/goals/batch",
            json={"goals": [_goal_payload(e.id) for e in exercises]},
            headers=headers,
        )

        # Pydantic rejects the oversized list with 422 at the schema layer.
        assert resp.status_code == 422

    def test_batch_creation_validates_all_exercises(self, client, db, auth_headers):
        headers, _user = auth_headers()
        real = _seed_exercise(db, id="ex-real-1", name="Real")

        resp = client.post(
            "/goals/batch",
            json={
                "goals": [
                    _goal_payload(real.id),
                    _goal_payload("nonexistent-exercise-id"),
                ]
            },
            headers=headers,
        )

        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"].lower()


class TestGoalCreationValidation:
    """Schema-level validation on POST /goals."""

    def test_exercise_id_required(self, client, auth_headers):
        headers, _user = auth_headers()
        resp = client.post(
            "/goals",
            json={
                "target_weight": 225,
                "weight_unit": "lb",
                "deadline": (date.today() + timedelta(weeks=12)).isoformat(),
            },
            headers=headers,
        )
        assert resp.status_code == 422

    def test_exercise_must_exist(self, client, auth_headers):
        headers, _user = auth_headers()
        resp = client.post(
            "/goals",
            json=_goal_payload("fake-exercise-id"),
            headers=headers,
        )
        assert resp.status_code == 400
        assert "Exercise not found" in resp.json()["detail"]

    def test_target_weight_must_be_positive(self, client, db, auth_headers):
        headers, _user = auth_headers()
        ex = _seed_exercise(db)
        resp = client.post(
            "/goals",
            json=_goal_payload(ex.id, target_weight=-10),
            headers=headers,
        )
        assert resp.status_code == 422

    def test_target_reps_must_be_positive(self, client, db, auth_headers):
        headers, _user = auth_headers()
        ex = _seed_exercise(db)
        resp = client.post(
            "/goals",
            json=_goal_payload(ex.id, target_reps=0),
            headers=headers,
        )
        assert resp.status_code == 422


class TestGoalListing:
    """GET /goals."""

    def test_list_returns_active_goals_by_default(self, client, db, auth_headers):
        headers, _user = auth_headers()
        ex = _seed_exercise(db)
        client.post("/goals", json=_goal_payload(ex.id), headers=headers)

        resp = client.get("/goals", headers=headers)

        assert resp.status_code == 200
        body = resp.json()
        assert body["active_count"] == 1
        assert body["max_goals"] == MAX_ACTIVE_GOALS
        assert body["can_add_more"] is True
        assert len(body["goals"]) == 1

    def test_list_includes_counts(self, client, db, auth_headers):
        headers, _user = auth_headers()
        for i in range(3):
            ex = _seed_exercise(db, id=f"ex-list-{i}", name=f"Ex {i}")
            client.post("/goals", json=_goal_payload(ex.id), headers=headers)

        resp = client.get("/goals", headers=headers)

        assert resp.status_code == 200
        body = resp.json()
        assert body["active_count"] == 3
        assert body["completed_count"] == 0
        assert body["can_add_more"] is True


class TestGoalUpdates:
    """PUT /goals/{id}."""

    def test_update_target_weight(self, client, db, auth_headers):
        headers, _user = auth_headers()
        ex = _seed_exercise(db)
        created = client.post("/goals", json=_goal_payload(ex.id), headers=headers).json()

        resp = client.put(
            f"/goals/{created['id']}",
            json={"target_weight": 250},
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["target_weight"] == 250

    def test_update_deadline(self, client, db, auth_headers):
        headers, _user = auth_headers()
        ex = _seed_exercise(db)
        created = client.post("/goals", json=_goal_payload(ex.id), headers=headers).json()
        new_deadline = (date.today() + timedelta(weeks=16)).isoformat()

        resp = client.put(
            f"/goals/{created['id']}",
            json={"deadline": new_deadline},
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["deadline"] == new_deadline

    def test_cannot_update_other_users_goal(self, client, db, auth_headers):
        headers_a, _user_a = auth_headers(email="a@example.com")
        ex = _seed_exercise(db)
        created = client.post("/goals", json=_goal_payload(ex.id), headers=headers_a).json()

        headers_b, _user_b = auth_headers(email="b@example.com")
        resp = client.put(
            f"/goals/{created['id']}",
            json={"target_weight": 999},
            headers=headers_b,
        )

        assert resp.status_code == 404

    def test_invalid_status_rejected(self, client, db, auth_headers):
        headers, _user = auth_headers()
        ex = _seed_exercise(db)
        created = client.post("/goals", json=_goal_payload(ex.id), headers=headers).json()

        resp = client.put(
            f"/goals/{created['id']}",
            json={"status": "invalid_status"},
            headers=headers,
        )

        assert resp.status_code == 400


class TestGoalDeletion:
    """DELETE /goals/{id} — abandon goal."""

    def test_abandon_active_goal(self, client, db, auth_headers):
        headers, _user = auth_headers()
        ex = _seed_exercise(db)
        created = client.post("/goals", json=_goal_payload(ex.id), headers=headers).json()

        resp = client.delete(f"/goals/{created['id']}", headers=headers)

        assert resp.status_code == 200

        # Confirm it was removed from the active list.
        list_resp = client.get("/goals", headers=headers)
        assert list_resp.json()["active_count"] == 0

    def test_cannot_abandon_already_abandoned_goal(self, client, db, auth_headers):
        headers, _user = auth_headers()
        ex = _seed_exercise(db)
        created = client.post("/goals", json=_goal_payload(ex.id), headers=headers).json()
        client.delete(f"/goals/{created['id']}", headers=headers)

        resp = client.delete(f"/goals/{created['id']}", headers=headers)

        assert resp.status_code == 400


# ============================================================================
# TODO: Previous pseudo-tests removed because they asserted on hand-built
# Python lists rather than real API behavior. The gaps below need coverage
# via new endpoints or service-level tests:
#
# - TODO: progress calculation (was TestGoalProgress) — needs an endpoint like
#   GET /goals/{id}/progress to return progress_percent; the endpoint exists
#   but returns a chart payload, not a simple percent — write a service-level
#   test against compute_goal_progress once its signature stabilizes.
# - TODO: "completed_goals_dont_count_towards_limit" — no API to mark a goal
#   as completed directly; completion is driven by PR detection. Cover with
#   an integration test once the PR-completion path is testable end-to-end.
# - TODO: weeks_remaining calculation — covered indirectly by GoalResponse
#   fields but no dedicated endpoint test yet.
# ============================================================================
