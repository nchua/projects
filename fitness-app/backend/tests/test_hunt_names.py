"""
Hunt names: suggestion logic + name field through the workout API.

Unit-tests hunt_name_service.suggest_hunt_name, then drives the API:
- POST /workouts stores a custom name (and blank names normalize to NULL)
- GET /workouts + GET /workouts/{id} return name and suggested_name
- PUT /workouts/{id} renames and "" clears back to the suggestion fallback
- WHOOP activity rows suggest the title-cased activity type
"""
import pytest

from app.services.hunt_name_service import suggest_hunt_name


class TestSuggestHuntName:
    def test_activity_type_wins_and_title_cases(self):
        assert suggest_hunt_name("TENNIS", ["Back", "Biceps"]) == "Tennis"

    def test_activity_type_already_titled_kept_verbatim(self):
        assert suggest_hunt_name("Outdoor Cycling", []) == "Outdoor Cycling"

    def test_single_muscle(self):
        assert suggest_hunt_name(None, ["Chest"]) == "Chest Day"

    def test_back_and_biceps(self):
        assert suggest_hunt_name(None, ["Back", "Lats", "Biceps"]) == "Back & Biceps Day"

    def test_leg_day_from_lower_body_muscles(self):
        assert suggest_hunt_name(None, ["Quads", "Hamstrings", "Glutes", "Calves"]) == "Leg Day"

    def test_push_day(self):
        assert suggest_hunt_name(None, ["Chest", "Front Delts", "Triceps"]) == "Push Day"

    def test_pull_day(self):
        assert suggest_hunt_name(None, ["Back", "Traps", "Biceps", "Forearms"]) == "Pull Day"

    def test_upper_body_day(self):
        assert suggest_hunt_name(None, ["Chest", "Back", "Shoulders", "Biceps"]) == "Upper Body Day"

    def test_full_body_when_upper_and_lower_mix(self):
        assert suggest_hunt_name(None, ["Chest", "Back", "Quads", "Shoulders"]) == "Full Body Day"

    def test_core_dropped_when_specific_muscles_present(self):
        assert suggest_hunt_name(None, ["Chest", "Abs", "Obliques"]) == "Chest Day"

    def test_core_only(self):
        assert suggest_hunt_name(None, ["Abs", "Obliques", "Lower Abs"]) == "Core Day"

    def test_full_body_exercise_only(self):
        assert suggest_hunt_name(None, ["Full Body"]) == "Full Body Day"

    def test_no_signal_returns_none(self):
        assert suggest_hunt_name(None, []) is None
        assert suggest_hunt_name("", None) is None

    def test_case_insensitive_muscle_normalization(self):
        # One seed row carries lowercase "chest"
        assert suggest_hunt_name(None, ["chest", "Triceps"]) == "Chest & Triceps Day"


@pytest.fixture
def named_exercises(db):
    """Seed a back and a biceps exercise; return their ids."""
    from app.models.exercise import Exercise
    back = Exercise(
        name="Barbell Row", is_custom=False, category="Pull", primary_muscle="Back"
    )
    biceps = Exercise(
        name="Barbell Curl", is_custom=False, category="Pull", primary_muscle="Biceps"
    )
    db.add_all([back, biceps])
    db.commit()
    return back.id, biceps.id


def _payload(exercise_ids, *, name=None, notes=None):
    body = {
        "date": "2026-07-19",
        "exercises": [
            {
                "exercise_id": ex_id,
                "order_index": i,
                "sets": [{"weight": 100, "weight_unit": "lb", "reps": 8, "set_number": 1}],
            }
            for i, ex_id in enumerate(exercise_ids)
        ],
    }
    if name is not None:
        body["name"] = name
    if notes is not None:
        body["notes"] = notes
    return body


class TestHuntNameAPI:
    def test_create_stores_custom_name_and_suggested_name(
        self, client, auth_headers, unique_email, named_exercises
    ):
        headers, _ = auth_headers(email=unique_email("hunt-name-create"))
        resp = client.post(
            "/workouts",
            json=_payload(named_exercises, name="Heavy Row Night"),
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        workout = resp.json()["workout"]
        assert workout["name"] == "Heavy Row Night"
        assert workout["suggested_name"] == "Back & Biceps Day"

        listed = client.get("/workouts", headers=headers).json()
        assert listed[0]["name"] == "Heavy Row Night"
        assert listed[0]["suggested_name"] == "Back & Biceps Day"

    def test_create_without_name_leaves_null_with_suggestion(
        self, client, auth_headers, unique_email, named_exercises
    ):
        headers, _ = auth_headers(email=unique_email("hunt-name-null"))
        resp = client.post(
            "/workouts", json=_payload(named_exercises, name="   "), headers=headers
        )
        assert resp.status_code == 201, resp.text
        workout = resp.json()["workout"]
        assert workout["name"] is None
        assert workout["suggested_name"] == "Back & Biceps Day"

    def test_put_renames_and_empty_string_clears(
        self, client, auth_headers, unique_email, named_exercises
    ):
        headers, _ = auth_headers(email=unique_email("hunt-name-rename"))
        workout = client.post(
            "/workouts", json=_payload(named_exercises), headers=headers
        ).json()["workout"]

        renamed = client.put(
            f"/workouts/{workout['id']}", json={"name": "Pull PR Attempt"}, headers=headers
        )
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["name"] == "Pull PR Attempt"

        detail = client.get(f"/workouts/{workout['id']}", headers=headers).json()
        assert detail["name"] == "Pull PR Attempt"
        assert detail["suggested_name"] == "Back & Biceps Day"

        cleared = client.put(
            f"/workouts/{workout['id']}", json={"name": ""}, headers=headers
        )
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["name"] is None

    def test_name_max_length_rejected(
        self, client, auth_headers, unique_email, named_exercises
    ):
        headers, _ = auth_headers(email=unique_email("hunt-name-long"))
        resp = client.post(
            "/workouts", json=_payload(named_exercises, name="x" * 101), headers=headers
        )
        assert resp.status_code == 422

    def test_whoop_activity_suggests_title_cased_type(
        self, client, db, auth_headers, unique_email
    ):
        """A set-less WHOOP activity row suggests its activity type."""
        from datetime import datetime, timezone

        from app.models.workout import WorkoutSession

        headers, user = auth_headers(email=unique_email("hunt-name-whoop"))
        session = WorkoutSession(
            user_id=user.id,
            date=datetime(2026, 7, 18, tzinfo=timezone.utc),
            notes="TENNIS - WHOOP Activity | Strain: 12.5 | Calories: 480",
        )
        db.add(session)
        db.commit()

        listed = client.get("/workouts", headers=headers).json()
        row = next(w for w in listed if w["id"] == session.id)
        assert row["is_activity"] is True
        assert row["suggested_name"] == "Tennis"
        assert row["name"] is None
