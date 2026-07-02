"""
End-to-end tests for the screenshot processing pipeline.

Mocks `anthropic.Anthropic` (via the shared `mock_anthropic` conftest fixture)
to return deterministic fixtures so we can test the real
extraction -> matching -> save flow against a real SQLite DB.

Covers:
- Gym workout multi-exercise, multi-set extraction saved as a WorkoutSession
- Warmup set handling (include_warmups=False strips warmup sets)
- WHOOP/Pickleball activity extraction (PR #3 regression) saved as
  both a DailyActivity AND a WorkoutSession, with heart-rate zones
  passed through in the response
- Exercises matched by fuzzy name ("Bench Press" -> canonical DB row)
- PR detection is wired in (first-ever set generates a PR row)
"""
from unittest.mock import patch

import pytest

from app.models.activity import DailyActivity
from app.models.exercise import Exercise
from app.models.pr import PR
from app.models.workout import Set, WorkoutExercise, WorkoutSession

pytestmark = pytest.mark.usefixtures("anthropic_api_key")


@pytest.fixture
def grant_unlimited_scans(seed_scan_balance):
    """Give a user unlimited scans so the rate-limiter doesn't block tests."""

    def _grant(user_id: str):
        return seed_scan_balance(user_id, credits=999, has_unlimited=True)

    return _grant


# ============ Fixtures: extraction payloads ============

GYM_WORKOUT_PAYLOAD = """
{
  "screenshot_type": "gym_workout",
  "session_date": "2025-04-15",
  "session_name": "Upper A",
  "duration_minutes": 62,
  "summary": {"tonnage_lb": 12450, "total_reps": 48},
  "exercises": [
    {
      "name": "Bench Press",
      "equipment": "barbell",
      "variation": null,
      "sets": [
        {"weight_lb": 95, "reps": 10, "sets": 1, "is_warmup": true},
        {"weight_lb": 185, "reps": 5, "sets": 1, "is_warmup": false},
        {"weight_lb": 205, "reps": 3, "sets": 1, "is_warmup": false},
        {"weight_lb": 225, "reps": 1, "sets": 1, "is_warmup": false}
      ],
      "total_reps": 19,
      "total_volume_lb": 2320
    },
    {
      "name": "Barbell Row",
      "equipment": "barbell",
      "variation": null,
      "sets": [
        {"weight_lb": 135, "reps": 8, "sets": 3, "is_warmup": false}
      ],
      "total_reps": 24,
      "total_volume_lb": 3240
    }
  ]
}
"""

WHOOP_PICKLEBALL_PAYLOAD = """
{
  "screenshot_type": "whoop_activity",
  "activity_type": "Pickleball",
  "session_date": "2025-04-15",
  "time_range": "6:30 PM to 7:45 PM",
  "duration_minutes": 75,
  "strain": 11.4,
  "steps": 3200,
  "calories": 612,
  "avg_hr": 132,
  "max_hr": 168,
  "source": "VIA APPLE WATCH",
  "heart_rate_zones": [
    {"zone": 2, "bpm_range": "110-130", "percentage": 45.0, "duration": "33:45"},
    {"zone": 3, "bpm_range": "130-150", "percentage": 35.0, "duration": "26:15"}
  ]
}
"""


# ============ Tests ============

class TestScreenshotGymWorkout:
    def test_gym_workout_saves_session_exercises_and_sets(
        self, client, db, auth_headers, seeded_exercises, grant_unlimited_scans,
        mock_anthropic, png_bytes
    ):
        headers, user = auth_headers(email="gym@example.com")
        grant_unlimited_scans(user.id)

        mock_ctor = mock_anthropic(GYM_WORKOUT_PAYLOAD)

        with patch("app.services.screenshot_service.anthropic.Anthropic", mock_ctor):
            response = client.post(
                "/screenshot/process",
                headers=headers,
                files={"file": ("workout.png", png_bytes, "image/png")},
                data={"save_workout": "true", "include_warmups": "true"},
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["screenshot_type"] == "gym_workout"
        assert body["workout_saved"] is True
        assert body["workout_id"] is not None

        # Session persisted
        session = db.query(WorkoutSession).filter_by(id=body["workout_id"]).first()
        assert session is not None
        assert session.user_id == user.id
        assert session.duration_minutes == 62

        # Two exercises saved, matched
        exercises = (
            db.query(WorkoutExercise)
            .filter_by(session_id=session.id)
            .order_by(WorkoutExercise.order_index)
            .all()
        )
        assert len(exercises) == 2

        bench = exercises[0]
        row = exercises[1]

        # Matched exercise IDs resolve to real Exercise rows
        bench_ex = db.query(Exercise).filter_by(id=bench.exercise_id).first()
        row_ex = db.query(Exercise).filter_by(id=row.exercise_id).first()
        assert bench_ex is not None
        assert "bench" in bench_ex.name.lower()
        assert row_ex is not None
        assert "row" in row_ex.name.lower()

        # Set counts:
        # Bench: 1 warmup + 3 working sets = 4
        # Row: 3 working sets (weight, reps expanded from sets=3)
        bench_sets = db.query(Set).filter_by(workout_exercise_id=bench.id).all()
        row_sets = db.query(Set).filter_by(workout_exercise_id=row.id).all()
        assert len(bench_sets) == 4
        assert len(row_sets) == 3

        # Heaviest-weight bench set is 225x1
        heaviest_by_weight = max(bench_sets, key=lambda s: s.weight)
        assert heaviest_by_weight.weight == 225
        assert heaviest_by_weight.reps == 1
        assert heaviest_by_weight.e1rm == pytest.approx(225.0, rel=1e-6)

        # Best e1RM on this day is 205x3 (Epley = 225.5), not 225x1.
        top_e1rm = max(bench_sets, key=lambda s: s.e1rm or 0)
        assert top_e1rm.e1rm == pytest.approx(225.5, rel=1e-6)

        # PR detection fired — at least one PR row exists for this user on bench
        prs = db.query(PR).filter(PR.user_id == user.id, PR.exercise_id == bench.exercise_id).all()
        assert len(prs) >= 1

    def test_gym_workout_excludes_warmups_when_flag_false(
        self, client, db, auth_headers, seeded_exercises, grant_unlimited_scans,
        mock_anthropic, png_bytes
    ):
        headers, user = auth_headers(email="nowarmup@example.com")
        grant_unlimited_scans(user.id)

        mock_ctor = mock_anthropic(GYM_WORKOUT_PAYLOAD)

        with patch("app.services.screenshot_service.anthropic.Anthropic", mock_ctor):
            response = client.post(
                "/screenshot/process",
                headers=headers,
                files={"file": ("workout.png", png_bytes, "image/png")},
                data={"save_workout": "true", "include_warmups": "false"},
            )

        assert response.status_code == 200
        body = response.json()
        session = db.query(WorkoutSession).filter_by(id=body["workout_id"]).first()

        bench = (
            db.query(WorkoutExercise)
            .filter_by(session_id=session.id, order_index=0)
            .first()
        )
        # Without warmups: only 3 working sets remain (95 lb x 10 warmup is stripped)
        bench_sets = db.query(Set).filter_by(workout_exercise_id=bench.id).all()
        assert len(bench_sets) == 3
        assert all(s.weight >= 185 for s in bench_sets)


class TestScreenshotWhoopActivity:
    def test_pickleball_whoop_screenshot_creates_activity_and_workout(
        self, client, db, auth_headers, seeded_exercises, grant_unlimited_scans,
        mock_anthropic, png_bytes
    ):
        """Regression for PR #3: Pickleball WHOOP screenshot should save
        a DailyActivity AND a WorkoutSession so it shows on the calendar,
        and pass heart-rate zones through in the response."""
        headers, user = auth_headers(email="pickle@example.com")
        grant_unlimited_scans(user.id)

        mock_ctor = mock_anthropic(WHOOP_PICKLEBALL_PAYLOAD)
        with patch("app.services.screenshot_service.anthropic.Anthropic", mock_ctor):
            response = client.post(
                "/screenshot/process",
                headers=headers,
                files={"file": ("whoop.png", png_bytes, "image/png")},
                data={"save_workout": "true"},
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["screenshot_type"] == "whoop_activity"
        assert body["activity_type"] == "Pickleball"
        assert body["strain"] == 11.4
        assert body["activity_saved"] is True
        assert body["workout_saved"] is True  # WHOOP also creates a calendar-visible workout

        # Heart-rate zones passed through untouched
        zones = body["heart_rate_zones"]
        assert len(zones) == 2
        assert zones[0]["zone"] == 2
        assert zones[0]["bpm_range"] == "110-130"

        # DailyActivity row persisted with strain/calories
        activity = db.query(DailyActivity).filter_by(id=body["activity_id"]).first()
        assert activity is not None
        assert activity.user_id == user.id
        assert activity.source == "whoop_screenshot"
        assert activity.strain == pytest.approx(11.4)
        assert activity.active_calories == 612

        # WorkoutSession row persisted
        session = db.query(WorkoutSession).filter_by(id=body["workout_id"]).first()
        assert session is not None
        assert session.user_id == user.id
        assert session.duration_minutes == 75
        assert "Pickleball" in (session.notes or "")


class TestScreenshotErrorHandling:
    def test_rejects_invalid_content_type(
        self, client, auth_headers, seeded_exercises, grant_unlimited_scans
    ):
        headers, user = auth_headers(email="badmime@example.com")
        grant_unlimited_scans(user.id)

        response = client.post(
            "/screenshot/process",
            headers=headers,
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )
        assert response.status_code == 400
        assert "Invalid file type" in response.json()["detail"]

    def test_anthropic_json_decode_error_returns_422(
        self, client, auth_headers, seeded_exercises, grant_unlimited_scans,
        mock_anthropic, png_bytes
    ):
        """If Claude returns garbage the API should surface a 422."""
        headers, user = auth_headers(email="garbage@example.com")
        grant_unlimited_scans(user.id)

        mock_ctor = mock_anthropic("this is not json {")
        with patch("app.services.screenshot_service.anthropic.Anthropic", mock_ctor):
            response = client.post(
                "/screenshot/process",
                headers=headers,
                files={"file": ("workout.png", png_bytes, "image/png")},
            )
        assert response.status_code == 422
        assert "JSON" in response.json()["detail"] or "parse" in response.json()["detail"].lower()
