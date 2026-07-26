"""
Cardio metric extraction from activity screenshots.

Runs and rides surface distance, pace, elevation, cadence and power. These
tests cover the whole path for those metrics: extraction payload -> SI
normalization -> workout_sessions columns -> API response (both the list and
detail endpoints), plus the unit-conversion helpers in isolation.

The reference payload mirrors a real Apple Health outdoor-run screenshot:
2.46 MI at 9'19"/MI, 160 FT gain, 170 SPM, 230 W, 297 active / 334 total kcal.
"""
from unittest.mock import patch

import pytest

from app.models.workout import WorkoutSession
from app.services.screenshot_service import (
    extract_cardio_metrics,
    parse_pace_to_seconds,
)
from app.services.workout_stats import cardio_display_fields, format_pace

pytestmark = pytest.mark.usefixtures("anthropic_api_key")


@pytest.fixture
def grant_unlimited_scans(seed_scan_balance):
    def _grant(user_id: str):
        return seed_scan_balance(user_id, credits=999, has_unlimited=True)

    return _grant


APPLE_HEALTH_RUN_PAYLOAD = """
{
  "screenshot_type": "whoop_activity",
  "activity_type": "Outdoor Run",
  "session_date": "2026-07-26",
  "time_range": "10:38 AM to 11:05 AM",
  "duration_minutes": 23,
  "strain": null,
  "steps": null,
  "calories": 297,
  "active_calories": 297,
  "total_calories": 334,
  "distance": 2.46,
  "distance_unit": "mi",
  "avg_pace": "9'19\\"",
  "pace_unit": "/mi",
  "avg_speed": null,
  "speed_unit": null,
  "elevation_gain": 160,
  "elevation_unit": "ft",
  "avg_cadence": 170,
  "avg_power": 230,
  "avg_hr": 169,
  "max_hr": null,
  "source": "VIA APPLE WATCH",
  "heart_rate_zones": []
}
"""


class TestPaceParsing:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("9'19\"", 559),      # Apple Fitness
            ("9:19", 559),         # Strava / Garmin
            ("9m19s", 559),
            ("9'19\"/mi", 559),   # unit suffix tolerated
            ("5:00 per km", 300),
            (9.5, 570),            # bare minutes
            ("", None),
            ("not a pace", None),
            (None, None),
        ],
    )
    def test_parses_the_formats_activity_apps_render(self, raw, expected):
        assert parse_pace_to_seconds(raw) == expected

    def test_format_pace_round_trips(self):
        assert format_pace(559) == "9'19\""
        assert format_pace(600) == "10'00\""
        assert format_pace(None) is None
        assert format_pace(0) is None


class TestCardioNormalization:
    def test_imperial_screenshot_normalizes_to_si(self):
        metrics = extract_cardio_metrics(
            {
                "distance": 2.46, "distance_unit": "MI",
                "avg_pace": "9'19\"", "pace_unit": "/MI",
                "elevation_gain": 160, "elevation_unit": "FT",
                "avg_cadence": 170, "avg_power": 230,
                "active_calories": 297, "total_calories": 334,
            }
        )
        assert metrics["distance_meters"] == pytest.approx(3958.99, abs=0.1)
        assert metrics["elevation_gain_meters"] == pytest.approx(48.77, abs=0.1)
        assert metrics["avg_speed_mps"] == pytest.approx(2.879, abs=0.001)
        assert metrics["avg_cadence_spm"] == 170
        assert metrics["avg_power_watts"] == 230
        assert metrics["active_calories"] == 297
        assert metrics["total_calories"] == 334

    def test_metric_screenshot_normalizes_to_same_units(self):
        metrics = extract_cardio_metrics(
            {"distance": 5.0, "distance_unit": "km", "avg_speed": 12.0, "speed_unit": "kph"}
        )
        assert metrics["distance_meters"] == 5000.0
        assert metrics["avg_speed_mps"] == pytest.approx(3.333, abs=0.01)

    def test_speed_reading_wins_over_pace_when_both_present(self):
        metrics = extract_cardio_metrics(
            {
                "avg_speed": 10.0, "speed_unit": "mph",
                "avg_pace": "20:00", "pace_unit": "/mi",
            }
        )
        assert metrics["avg_speed_mps"] == pytest.approx(4.4704, abs=0.001)

    def test_stored_speed_comes_from_displayed_pace_not_distance_over_time(self):
        """Apps report moving pace; duration is elapsed. They must not be conflated."""
        metrics = extract_cardio_metrics(
            {
                "distance": 2.46, "distance_unit": "mi",
                "avg_pace": "9'19\"", "pace_unit": "/mi",
            }
        )
        derived_from_elapsed = 3958.99 / (26 * 60 + 50)  # 26:50 elapsed
        assert metrics["avg_speed_mps"] != pytest.approx(derived_from_elapsed, abs=0.05)
        assert metrics["avg_speed_mps"] == pytest.approx(2.879, abs=0.001)

    def test_unknown_unit_is_dropped_not_guessed(self):
        assert extract_cardio_metrics({"distance": 5, "distance_unit": "furlongs"}) == {}
        assert extract_cardio_metrics({"distance": 5, "distance_unit": None}) == {}

    def test_strength_screenshot_yields_no_cardio_metrics(self):
        assert extract_cardio_metrics({"screenshot_type": "gym_workout"}) == {}

    def test_legacy_single_calories_field_maps_to_active(self):
        assert extract_cardio_metrics({"calories": 400})["active_calories"] == 400

    def test_malformed_values_do_not_raise(self):
        metrics = extract_cardio_metrics(
            {
                "distance": "n/a", "distance_unit": "mi",
                "avg_cadence": "--", "avg_power": None,
                "elevation_gain": "", "elevation_unit": "ft",
            }
        )
        assert metrics == {}


class TestCardioDisplayFields:
    def test_si_columns_render_back_to_imperial(self):
        session = WorkoutSession(
            distance_meters=3958.99,
            elevation_gain_meters=48.77,
            avg_speed_mps=2.879,
            avg_cadence_spm=170,
            avg_power_watts=230,
            active_calories=297,
            total_calories=334,
        )
        fields = cardio_display_fields(session)
        assert fields["distance_miles"] == pytest.approx(2.46, abs=0.01)
        assert fields["elevation_gain_feet"] == 160
        assert fields["avg_pace_display"] == "9'19\""
        assert fields["avg_cadence_spm"] == 170
        assert fields["avg_power_watts"] == 230

    def test_strength_session_reports_every_field_as_none(self):
        fields = cardio_display_fields(WorkoutSession())
        assert set(fields) >= {
            "distance_meters", "distance_miles", "avg_pace_display",
            "elevation_gain_feet", "avg_cadence_spm", "avg_power_watts",
            "active_calories", "total_calories",
        }
        assert all(v is None for v in fields.values())


class TestCardioScreenshotEndToEnd:
    def test_run_screenshot_persists_and_returns_cardio_metrics(
        self, client, db, auth_headers, grant_unlimited_scans, mock_anthropic, png_bytes
    ):
        headers, user = auth_headers(email="runner@example.com")
        grant_unlimited_scans(user.id)

        mock_ctor = mock_anthropic(APPLE_HEALTH_RUN_PAYLOAD)
        with patch("app.services.screenshot_service.anthropic.Anthropic", mock_ctor):
            response = client.post(
                "/screenshot/process",
                headers=headers,
                files={"file": ("run.png", png_bytes, "image/png")},
                data={"save_workout": "true"},
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["workout_saved"] is True
        workout_id = body["workout_id"]

        # Persisted in SI on the session row
        session = db.query(WorkoutSession).filter_by(id=workout_id).first()
        assert session.distance_meters == pytest.approx(3958.99, abs=0.1)
        assert session.elevation_gain_meters == pytest.approx(48.77, abs=0.1)
        assert session.avg_speed_mps == pytest.approx(2.879, abs=0.001)
        assert session.avg_cadence_spm == 170
        assert session.avg_power_watts == 230
        assert session.active_calories == 297
        assert session.total_calories == 334

        # Detail endpoint renders imperial for the client
        detail = client.get(f"/workouts/{workout_id}", headers=headers)
        assert detail.status_code == 200, detail.text
        payload = detail.json()
        assert payload["distance_miles"] == pytest.approx(2.46, abs=0.01)
        assert payload["avg_pace_display"] == "9'19\""
        assert payload["elevation_gain_feet"] == 160
        assert payload["avg_cadence_spm"] == 170
        assert payload["avg_power_watts"] == 230
        assert payload["total_calories"] == 334

        # List endpoint carries them too, so History rows can show distance
        listing = client.get("/workouts", headers=headers)
        assert listing.status_code == 200, listing.text
        row = next(w for w in listing.json() if w["id"] == workout_id)
        assert row["distance_miles"] == pytest.approx(2.46, abs=0.01)
        assert row["avg_pace_display"] == "9'19\""

    def test_strength_screenshot_leaves_cardio_columns_null(
        self, client, db, auth_headers, seeded_exercises, grant_unlimited_scans,
        mock_anthropic, png_bytes
    ):
        """Regression guard: the cardio columns must not leak into lifting sessions."""
        headers, user = auth_headers(email="lifter-cardio@example.com")
        grant_unlimited_scans(user.id)

        payload = """
        {
          "screenshot_type": "gym_workout",
          "session_date": "2026-07-26",
          "session_name": "Upper A",
          "duration_minutes": 45,
          "summary": {"tonnage_lb": 5000, "total_reps": 20},
          "exercises": [
            {"name": "Bench Press", "equipment": "barbell", "variation": null,
             "sets": [{"weight_lb": 185, "reps": 5, "sets": 1, "is_warmup": false}],
             "total_reps": 5, "total_volume_lb": 925}
          ]
        }
        """
        mock_ctor = mock_anthropic(payload)
        with patch("app.services.screenshot_service.anthropic.Anthropic", mock_ctor):
            response = client.post(
                "/screenshot/process",
                headers=headers,
                files={"file": ("lift.png", png_bytes, "image/png")},
                data={"save_workout": "true"},
            )

        assert response.status_code == 200, response.text
        session = db.query(WorkoutSession).filter_by(id=response.json()["workout_id"]).first()
        assert session.distance_meters is None
        assert session.avg_speed_mps is None
        assert session.elevation_gain_meters is None
        assert session.avg_cadence_spm is None
        assert session.avg_power_watts is None
