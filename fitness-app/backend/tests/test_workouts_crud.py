"""
API-level CRUD tests for PUT /workouts/{id} and DELETE /workouts/{id}.

Ports the scenario matrices of test-workout-update.js and
test-workout-delete.js to pytest, and adds:
- workout-date round trips through the REAL WorkoutCreate.parse_date
  validator + to_iso8601_utc (replacing the deleted inline-strptime
  simulation tests in test_date_formatting.py)
- WHOOP-notes rendering in GET /workouts (guards the parse_whoop_notes
  wiring in api/workouts.py)
"""
from datetime import datetime, timezone

import pytest

from app.models.workout import Set, WorkoutSession

NONEXISTENT_WORKOUT_ID = "00000000-0000-0000-0000-000000000000"


@pytest.fixture
def seeded_exercise(db):
    """Insert one seeded (loadable) exercise row and return its id."""
    from app.models.exercise import Exercise
    ex = Exercise(name="Bench Press", is_custom=False, category="Push")
    db.add(ex)
    db.commit()
    return ex.id


@pytest.fixture
def seeded_cardio_exercise(db):
    """Insert one non-loadable (Cardio) exercise row and return its id.

    Cardio never mints PRs (see pr_detection.is_loadable_exercise). That
    matters for the PUT replace-exercises test: prs.set_id has no ondelete,
    so bulk-deleting sets that a PR row points at trips the FK constraint
    (known latent bug in the PUT handler — do not "fix" the test by
    asserting the 500).
    """
    from app.models.exercise import Exercise
    ex = Exercise(name="Rowing Machine", is_custom=False, category="Cardio")
    db.add(ex)
    db.commit()
    return ex.id


def _workout_payload(exercise_id: str, *, date: str = "2026-04-19", sets: list = None) -> dict:
    return {
        "date": date,
        "duration_minutes": 60,
        "notes": "Original notes",
        "exercises": [
            {
                "exercise_id": exercise_id,
                "order_index": 0,
                "sets": sets or [
                    {"weight": 135, "weight_unit": "lb", "reps": 10, "set_number": 1},
                    {"weight": 135, "weight_unit": "lb", "reps": 8, "set_number": 2},
                ],
            }
        ],
    }


def _create_workout(client, headers, payload) -> dict:
    resp = client.post("/workouts", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["workout"]


class TestUpdateWorkout:
    def test_replace_exercises_recalculates_e1rm_and_purges_old_sets(
        self, client, db, auth_headers, unique_email, seeded_cardio_exercise
    ):
        """PUT with an exercises payload replaces ALL exercises/sets: the
        response carries freshly calculated e1RMs and the old Set rows are
        removed from the DB via the bulk WorkoutExercise delete + FK cascade
        (not merely omitted from the response)."""
        headers, _ = auth_headers(email=unique_email("put-replace"))
        workout = _create_workout(
            client, headers, _workout_payload(seeded_cardio_exercise)
        )
        old_set_ids = [s["id"] for ex in workout["exercises"] for s in ex["sets"]]
        assert len(old_set_ids) == 2

        resp = client.put(
            f"/workouts/{workout['id']}",
            json={
                "exercises": [
                    {
                        "exercise_id": seeded_cardio_exercise,
                        "order_index": 0,
                        "sets": [
                            {"weight": 225, "weight_unit": "lb", "reps": 5, "set_number": 1},
                        ],
                    }
                ]
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        sets = resp.json()["exercises"][0]["sets"]
        assert len(sets) == 1
        # Epley (default formula): 225 * (1 + 5/30) = 262.5
        assert sets[0]["e1rm"] == pytest.approx(262.5)
        assert sets[0]["id"] not in old_set_ids

        # The old Set rows must be GONE from the DB — this is the
        # bulk-delete + FK-cascade path (WorkoutExercise deleted directly;
        # sets fall via ondelete CASCADE).
        db.expire_all()
        assert db.query(Set).filter(Set.id.in_(old_set_ids)).count() == 0

    def test_basic_field_update_preserves_exercises(
        self, client, auth_headers, unique_email, seeded_exercise
    ):
        """PUT with only notes/duration must leave exercises and sets intact
        (same rows, not recreated)."""
        headers, _ = auth_headers(email=unique_email("put-basic"))
        workout = _create_workout(client, headers, _workout_payload(seeded_exercise))
        original_set_ids = {
            s["id"] for ex in workout["exercises"] for s in ex["sets"]
        }

        resp = client.put(
            f"/workouts/{workout['id']}",
            json={"notes": "Updated notes - feeling strong!", "duration_minutes": 75},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["notes"] == "Updated notes - feeling strong!"
        assert data["duration_minutes"] == 75
        assert len(data["exercises"]) == 1
        assert len(data["exercises"][0]["sets"]) == 2
        assert {s["id"] for s in data["exercises"][0]["sets"]} == original_set_ids

    def test_update_other_users_workout_returns_404(
        self, client, auth_headers, unique_email, seeded_exercise
    ):
        headers_owner, _ = auth_headers(email=unique_email("put-owner"))
        workout = _create_workout(client, headers_owner, _workout_payload(seeded_exercise))

        headers_other, _ = auth_headers(email=unique_email("put-other"))
        resp = client.put(
            f"/workouts/{workout['id']}",
            json={"notes": "hijack attempt"},
            headers=headers_other,
        )
        assert resp.status_code == 404

    def test_update_soft_deleted_workout_returns_404(
        self, client, auth_headers, unique_email, seeded_exercise
    ):
        headers, _ = auth_headers(email=unique_email("put-deleted"))
        workout = _create_workout(client, headers, _workout_payload(seeded_exercise))
        assert client.delete(f"/workouts/{workout['id']}", headers=headers).status_code == 204

        resp = client.put(
            f"/workouts/{workout['id']}",
            json={"notes": "should not update"},
            headers=headers,
        )
        assert resp.status_code == 404


class TestDeleteWorkout:
    def test_soft_delete_matrix(self, client, auth_headers, unique_email, seeded_exercise):
        """Port of test-workout-delete.js: DELETE -> 204, gone from list and
        detail, re-DELETE -> 404, and a sibling workout survives untouched."""
        headers, _ = auth_headers(email=unique_email("del-matrix"))
        keep = _create_workout(
            client, headers, _workout_payload(seeded_exercise, date="2026-04-18")
        )
        doomed = _create_workout(
            client, headers, _workout_payload(seeded_exercise, date="2026-04-19")
        )

        # Both visible before deletion.
        ids_before = {w["id"] for w in client.get("/workouts", headers=headers).json()}
        assert {keep["id"], doomed["id"]} <= ids_before

        # DELETE -> 204 No Content.
        resp = client.delete(f"/workouts/{doomed['id']}", headers=headers)
        assert resp.status_code == 204, resp.text

        # Excluded from the list; sibling still present.
        ids_after = {w["id"] for w in client.get("/workouts", headers=headers).json()}
        assert doomed["id"] not in ids_after
        assert keep["id"] in ids_after

        # Detail GET -> 404.
        assert client.get(f"/workouts/{doomed['id']}", headers=headers).status_code == 404

        # Re-DELETE -> 404 (already soft-deleted).
        assert client.delete(f"/workouts/{doomed['id']}", headers=headers).status_code == 404

        # Sibling survives with its exercises/sets intact.
        sibling = client.get(f"/workouts/{keep['id']}", headers=headers)
        assert sibling.status_code == 200
        assert len(sibling.json()["exercises"]) == 1
        assert len(sibling.json()["exercises"][0]["sets"]) == 2

    def test_delete_nonexistent_workout_returns_404(self, client, auth_headers, unique_email):
        headers, _ = auth_headers(email=unique_email("del-missing"))
        resp = client.delete(f"/workouts/{NONEXISTENT_WORKOUT_ID}", headers=headers)
        assert resp.status_code == 404

    def test_delete_other_users_workout_returns_404(
        self, client, auth_headers, unique_email, seeded_exercise
    ):
        headers_owner, _ = auth_headers(email=unique_email("del-owner"))
        workout = _create_workout(client, headers_owner, _workout_payload(seeded_exercise))

        headers_other, _ = auth_headers(email=unique_email("del-other"))
        resp = client.delete(f"/workouts/{workout['id']}", headers=headers_other)
        assert resp.status_code == 404

        # Owner still sees it.
        assert client.get(f"/workouts/{workout['id']}", headers=headers_owner).status_code == 200


class TestWorkoutDateRoundTrip:
    """Round trip through the REAL WorkoutCreate.parse_date validator and
    to_iso8601_utc — the endpoint-level version of the date contract in
    test_date_formatting.py (a "Feb 1" workout must come back as "Feb 1",
    never shifted by a timezone conversion)."""

    def test_date_only_string_round_trips_exactly(
        self, client, auth_headers, unique_email, seeded_exercise
    ):
        headers, _ = auth_headers(email=unique_email("date-only"))
        workout = _create_workout(
            client, headers, _workout_payload(seeded_exercise, date="2026-02-01")
        )
        assert workout["date"] == "2026-02-01"

        fetched = client.get(f"/workouts/{workout['id']}", headers=headers)
        assert fetched.status_code == 200
        assert fetched.json()["date"] == "2026-02-01"
        assert "T" not in fetched.json()["date"]
        assert "Z" not in fetched.json()["date"]

    def test_full_iso_datetime_returns_date_only_string(
        self, client, auth_headers, unique_email, seeded_exercise
    ):
        """A full ISO datetime exercises parse_date's fromisoformat branch;
        midnight collapses back to a date-only string on the way out."""
        headers, _ = auth_headers(email=unique_email("date-iso"))
        workout = _create_workout(
            client, headers,
            _workout_payload(seeded_exercise, date="2026-02-01T00:00:00Z"),
        )

        fetched = client.get(f"/workouts/{workout['id']}", headers=headers)
        assert fetched.status_code == 200
        assert fetched.json()["date"] == "2026-02-01"


class TestLocalDate:
    """workout_sessions.local_date — the explicit local calendar day.

    Derived from the midnight convention when the client doesn't send it,
    authoritative when it does (a watch workout at Sat 02:00 UTC is still
    Friday for the lifter)."""

    def test_derived_from_date_only_create(
        self, client, auth_headers, unique_email, seeded_exercise
    ):
        headers, _ = auth_headers(email=unique_email("ld-derive"))
        workout = _create_workout(
            client, headers, _workout_payload(seeded_exercise, date="2026-02-01")
        )
        assert workout["local_date"] == "2026-02-01"

    def test_explicit_local_date_wins_over_utc_timestamp(
        self, client, auth_headers, unique_email, seeded_exercise
    ):
        headers, _ = auth_headers(email=unique_email("ld-explicit"))
        payload = _workout_payload(seeded_exercise, date="2026-02-01T02:30:00Z")
        payload["local_date"] = "2026-01-31"
        workout = _create_workout(client, headers, payload)
        assert workout["local_date"] == "2026-01-31"

        fetched = client.get(f"/workouts/{workout['id']}", headers=headers)
        assert fetched.json()["local_date"] == "2026-01-31"

    def test_non_midnight_without_explicit_stays_null(
        self, client, auth_headers, unique_email, seeded_exercise
    ):
        headers, _ = auth_headers(email=unique_email("ld-null"))
        workout = _create_workout(
            client, headers,
            _workout_payload(seeded_exercise, date="2026-02-01T02:30:00Z"),
        )
        assert workout["local_date"] is None

    def test_update_date_rederives_local_date(
        self, client, auth_headers, unique_email, seeded_exercise
    ):
        headers, _ = auth_headers(email=unique_email("ld-update"))
        workout = _create_workout(
            client, headers, _workout_payload(seeded_exercise, date="2026-02-01")
        )

        resp = client.put(
            f"/workouts/{workout['id']}", json={"date": "2026-02-03"}, headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["local_date"] == "2026-02-03"

        resp = client.put(
            f"/workouts/{workout['id']}",
            json={"date": "2026-02-05T02:30:00Z", "local_date": "2026-02-04"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["local_date"] == "2026-02-04"

    def test_summary_list_includes_local_date(
        self, client, auth_headers, unique_email, seeded_exercise
    ):
        headers, _ = auth_headers(email=unique_email("ld-list"))
        _create_workout(
            client, headers, _workout_payload(seeded_exercise, date="2026-02-01")
        )
        listed = client.get("/workouts", headers=headers)
        assert listed.status_code == 200
        assert listed.json()[0]["local_date"] == "2026-02-01"


class TestWhoopNotesRendering:
    def test_whoop_activity_notes_render_in_list(
        self, client, auth_headers, unique_email, db
    ):
        """A WHOOP session (activity encoded in notes) must surface parsed
        activity fields in the GET /workouts list row."""
        headers, user = auth_headers(email=unique_email("whoop"))
        session = WorkoutSession(
            user_id=user.id,
            date=datetime.now(timezone.utc).replace(tzinfo=None),
            duration_minutes=60,
            notes="TENNIS - WHOOP Activity | Strain: 14.3 | Calories: 500",
        )
        db.add(session)
        db.commit()

        resp = client.get("/workouts", headers=headers)
        assert resp.status_code == 200, resp.text
        row = next(r for r in resp.json() if r["id"] == session.id)

        assert row["is_whoop_activity"] is True
        assert row["activity_type"] == "TENNIS"
        assert row["strain"] == pytest.approx(14.3)
        assert row["calories"] == 500
        # Set-less with a known activity type -> rendered as an activity.
        assert row["is_activity"] is True
