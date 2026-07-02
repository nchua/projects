"""
Tests for POST /screenshot/process/batch and merge_extractions.

The batch endpoint reserves len(files) credits UP FRONT (committed immediately
so the FOR UPDATE lock is released before the slow Anthropic calls), then
issues compensating refunds for failed extractions:
- partial failure -> refund exactly the failed count, still 200 with merged workout
- total failure   -> full refund, 504 (timeout) / 500
- validation errors (>10 files, bad content type) -> 400 BEFORE any credit is touched

merge_extractions combines per-screenshot extraction dicts into one workout.

Follows the mocking pattern of test_screenshot_e2e.py: mock the Anthropic
client (via the shared `mock_anthropic` conftest fixture), not HTTP.
"""
from unittest.mock import MagicMock, patch

import anthropic
import pytest
from sqlalchemy.orm import Session

from app.models.scan_balance import ScanBalance
from app.models.workout import WorkoutExercise, WorkoutSession
from app.services.screenshot_service import merge_extractions

pytestmark = pytest.mark.usefixtures("anthropic_api_key")


# ============ Fixtures ============

@pytest.fixture
def refund_sessions(db):
    """
    Point the batch refund path's fresh-session factory at the test transaction.

    The endpoint refunds via `_refund_scan_credits_safe(SessionLocal, ...)`,
    which opens a brand-new session per attempt. Under the test harness's
    StaticPool in-memory SQLite, a genuinely fresh session shares the test's
    single DBAPI connection, so its BEGIN collides with the test's outer
    transaction and the best-effort refund would swallow the error and appear
    to silently fail. Binding the factory to the test connection with
    savepoint-join (exactly how the request session itself is wired) keeps
    refunds visible to assertions and rolled back at teardown.
    """
    def _factory() -> Session:
        return Session(bind=db.get_bind(), join_transaction_mode="create_savepoint")

    with patch("app.api.screenshot.SessionLocal", _factory):
        yield


def _get_balance(db, user_id: str) -> int:
    db.expire_all()
    balance = db.query(ScanBalance).filter(ScanBalance.user_id == user_id).first()
    return balance.scan_credits


# ============ Extraction payloads ============

BENCH_PAYLOAD = {
    "screenshot_type": "gym_workout",
    "session_date": "2025-05-01",
    "session_name": "Push",
    "duration_minutes": 30,
    "summary": {"tonnage_lb": 925, "total_reps": 5},
    "exercises": [
        {
            "name": "Bench Press",
            "equipment": "barbell",
            "variation": None,
            "sets": [{"weight_lb": 185, "reps": 5, "sets": 1, "is_warmup": False}],
            "total_reps": 5,
            "total_volume_lb": 925,
        }
    ],
}

ROW_PAYLOAD = {
    "screenshot_type": "gym_workout",
    "session_date": "2025-05-01",
    "session_name": None,
    "duration_minutes": 25,
    "summary": {"tonnage_lb": 1080, "total_reps": 8},
    "exercises": [
        {
            "name": "Barbell Row",
            "equipment": "barbell",
            "variation": None,
            "sets": [{"weight_lb": 135, "reps": 8, "sets": 1, "is_warmup": False}],
            "total_reps": 8,
            "total_volume_lb": 1080,
        }
    ],
}


def _batch_files(png: bytes, count: int):
    return [
        ("files", (f"shot-{i}.png", png, "image/png"))
        for i in range(count)
    ]


# ============ Batch endpoint: credit reservation + refunds ============

class TestBatchCreditRefunds:
    def test_partial_failure_saves_merged_workout_and_refunds_failed_count(
        self, client, db, auth_headers, seeded_exercises, seed_scan_balance,
        mock_anthropic, png_bytes, refund_sessions
    ):
        """3 files, middle extraction times out -> 200, merged workout from the
        2 successes is saved, and exactly 1 credit is refunded (net -2)."""
        headers, user = auth_headers(email="batch-partial@example.com")
        seed_scan_balance(user.id, credits=10)

        mock_ctor = mock_anthropic(
            BENCH_PAYLOAD,
            anthropic.APITimeoutError(request=MagicMock()),
            ROW_PAYLOAD,
        )

        with patch("app.services.screenshot_service.anthropic.Anthropic", mock_ctor):
            response = client.post(
                "/screenshot/process/batch",
                headers=headers,
                files=_batch_files(png_bytes, 3),
                data={"save_workout": "true"},
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["screenshots_processed"] == 3
        assert body["screenshot_type"] == "gym_workout"
        # Merged: durations summed, exercises concatenated
        assert body["duration_minutes"] == 55
        assert [ex["name"] for ex in body["exercises"]] == ["Bench Press", "Barbell Row"]

        # Merged workout persisted with both exercises
        assert body["workout_saved"] is True
        session = db.query(WorkoutSession).filter_by(id=body["workout_id"]).first()
        assert session is not None
        assert session.user_id == user.id
        saved_exercises = db.query(WorkoutExercise).filter_by(session_id=session.id).all()
        assert len(saved_exercises) == 2

        # 3 reserved up front, 1 refunded for the failed file -> net 2 spent
        assert _get_balance(db, user.id) == 8

    def test_all_extractions_time_out_504_and_full_refund(
        self, client, db, auth_headers, seeded_exercises, seed_scan_balance,
        mock_anthropic, png_bytes, refund_sessions
    ):
        headers, user = auth_headers(email="batch-allfail@example.com")
        seed_scan_balance(user.id, credits=5)

        mock_ctor = mock_anthropic(anthropic.APITimeoutError(request=MagicMock()))

        with patch("app.services.screenshot_service.anthropic.Anthropic", mock_ctor):
            response = client.post(
                "/screenshot/process/batch",
                headers=headers,
                files=_batch_files(png_bytes, 3),
                data={"save_workout": "true"},
            )

        assert response.status_code == 504, response.text
        assert "timed out" in response.json()["detail"].lower()

        # All 3 reserved credits refunded
        assert _get_balance(db, user.id) == 5

    def test_more_than_ten_files_rejected_before_credits_touched(
        self, client, db, auth_headers, seed_scan_balance, mock_anthropic, png_bytes
    ):
        headers, user = auth_headers(email="batch-toomany@example.com")
        seed_scan_balance(user.id, credits=5)

        mock_ctor = mock_anthropic(BENCH_PAYLOAD)
        with patch("app.services.screenshot_service.anthropic.Anthropic", mock_ctor):
            response = client.post(
                "/screenshot/process/batch",
                headers=headers,
                files=_batch_files(png_bytes, 11),
                data={"save_workout": "true"},
            )

        assert response.status_code == 400
        assert "Maximum 10" in response.json()["detail"]
        mock_ctor.return_value.messages.create.assert_not_called()
        assert _get_balance(db, user.id) == 5

    def test_mixed_content_types_rejected_before_credits_touched(
        self, client, db, auth_headers, seed_scan_balance, mock_anthropic, png_bytes
    ):
        headers, user = auth_headers(email="batch-mixed@example.com")
        seed_scan_balance(user.id, credits=5)

        mock_ctor = mock_anthropic(BENCH_PAYLOAD)
        with patch("app.services.screenshot_service.anthropic.Anthropic", mock_ctor):
            response = client.post(
                "/screenshot/process/batch",
                headers=headers,
                files=[
                    ("files", ("shot.png", png_bytes, "image/png")),
                    ("files", ("notes.txt", b"not an image", "text/plain")),
                ],
                data={"save_workout": "true"},
            )

        assert response.status_code == 400
        assert "Invalid file type" in response.json()["detail"]
        mock_ctor.return_value.messages.create.assert_not_called()
        assert _get_balance(db, user.id) == 5


# ============ merge_extractions unit tests ============

def _gym_extraction(exercises=None, duration=None, session_date=None,
                    confidence="high", tonnage=0, total_reps=0):
    return {
        "screenshot_type": "gym_workout",
        "session_date": session_date,
        "session_name": None,
        "duration_minutes": duration,
        "summary": {"tonnage_lb": tonnage, "total_reps": total_reps},
        "exercises": exercises or [],
        "processing_confidence": confidence,
    }


def _whoop_extraction(strain=None, steps=None, calories=None, avg_hr=None,
                      max_hr=None, duration=None, activity_type="Pickleball",
                      confidence="high"):
    return {
        "screenshot_type": "whoop_activity",
        "activity_type": activity_type,
        "session_date": None,
        "time_range": None,
        "duration_minutes": duration,
        "strain": strain,
        "steps": steps,
        "calories": calories,
        "avg_hr": avg_hr,
        "max_hr": max_hr,
        "source": None,
        "heart_rate_zones": [],
        "processing_confidence": confidence,
        "exercises": [],
        "summary": {"tonnage_lb": 0, "total_reps": 0},
    }


class TestMergeExtractions:
    def test_concatenates_exercises_in_order(self):
        bench = {"name": "Bench Press", "sets": []}
        row = {"name": "Barbell Row", "sets": []}
        curl = {"name": "Barbell Curl", "sets": []}

        merged = merge_extractions([
            _gym_extraction(exercises=[bench, row]),
            _gym_extraction(exercises=[curl]),
        ])

        assert merged["exercises"] == [bench, row, curl]

    def test_sums_durations(self):
        merged = merge_extractions([
            _gym_extraction(duration=30),
            _gym_extraction(duration=45),
        ])
        assert merged["duration_minutes"] == 75

    def test_mixed_types_promote_to_whoop_activity(self):
        merged = merge_extractions([
            _gym_extraction(exercises=[{"name": "Bench Press", "sets": []}]),
            _whoop_extraction(strain=8.2, activity_type="Pickleball"),
        ])
        assert merged["screenshot_type"] == "whoop_activity"
        assert merged["activity_type"] == "Pickleball"
        assert merged["strain"] == pytest.approx(8.2)

    def test_aggregates_strain_steps_calories(self):
        merged = merge_extractions([
            _whoop_extraction(strain=5.5, steps=3000, calories=400),
            _whoop_extraction(strain=6.0, steps=2000, calories=250),
        ])
        assert merged["strain"] == pytest.approx(11.5)
        assert merged["steps"] == 5000
        assert merged["calories"] == 650

    def test_takes_max_of_avg_and_max_hr(self):
        merged = merge_extractions([
            _whoop_extraction(avg_hr=132, max_hr=175),
            _whoop_extraction(avg_hr=140, max_hr=168),
        ])
        assert merged["avg_hr"] == 140
        assert merged["max_hr"] == 175

    @pytest.mark.parametrize("confidences,expected", [
        pytest.param(["high", "high"], "high", id="all-high"),
        pytest.param(["high", "medium"], "medium", id="medium-downgrades"),
        pytest.param(["high", "medium", "low"], "low", id="low-wins"),
    ])
    def test_confidence_downgrades_to_worst(self, confidences, expected):
        merged = merge_extractions([
            _gym_extraction(confidence=c) for c in confidences
        ])
        assert merged["processing_confidence"] == expected
