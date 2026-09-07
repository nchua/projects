"""
Global Anthropic spend ceiling (app-store-launch spec §G4.1) and the
password-reset per-IP limit (§G4.2).

The ceiling sums today's vision calls across every user and refuses new
scans past ``ANTHROPIC_DAILY_CALL_CEILING`` with a 503 that debits nothing.
The owner is warned once a day on the way up and once a day at the cap.
"""
import io
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.api import screenshot as screenshot_api
from app.api.screenshot import SpendCeilingExceeded, _check_screenshot_rate_limit
from app.core.config import settings
from app.models.scan_balance import ScanBalance
from app.models.screenshot_usage import ScreenshotUsage

pytestmark = pytest.mark.usefixtures("anthropic_api_key")

CEILING = 10
WARN_PERCENT = 80  # warn threshold = 8 calls

# Pin the clock (see tests/test_screenshot_rate_limit.py): the ceiling counts
# usages since UTC midnight, so a fixed mid-day instant keeps every seeded
# usage inside one UTC day no matter when the suite runs.
FIXED_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


class _FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return FIXED_NOW if tz is not None else FIXED_NOW.replace(tzinfo=None)


MINIMAL_EXTRACTION = {
    "screenshot_type": "gym_workout",
    "session_date": "2026-01-15",
    "session_name": "Push",
    "duration_minutes": 40,
    "exercises": [
        {"name": "Bench Press", "sets": [{"weight_lb": 135, "reps": 5, "sets": 1}]}
    ],
    "processing_confidence": "high",
}


@pytest.fixture(autouse=True)
def _small_ceiling(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_DAILY_CALL_CEILING", CEILING)
    monkeypatch.setattr(settings, "ANTHROPIC_DAILY_CALL_WARN_PERCENT", WARN_PERCENT)
    monkeypatch.setattr(screenshot_api, "_spend_alert_sent_on", {})
    monkeypatch.setattr(screenshot_api, "datetime", _FrozenDateTime)


@pytest.fixture
def owner_alert():
    with patch("app.api.screenshot.send_owner_alert", return_value=True) as mock:
        yield mock


@pytest.fixture
def global_usage(db, create_test_user):
    """Record ``count`` vision calls today by an unrelated user."""

    def _seed(count: int) -> None:
        other, _ = create_test_user(email="everyone-else@example.com")
        db.add(
            ScreenshotUsage(
                user_id=other.id,
                screenshots_count=count,
                created_at=FIXED_NOW - timedelta(hours=1),
            )
        )
        db.commit()

    return _seed


def _png_upload(name: str = "shot.png"):
    from tests.conftest import make_png_bytes

    return (name, io.BytesIO(make_png_bytes()), "image/png")


def _balance(db, user_id: str) -> ScanBalance:
    db.expire_all()
    return db.query(ScanBalance).filter(ScanBalance.user_id == user_id).one()


class TestSpendCeiling:
    def test_under_ceiling_passes(self, db, create_test_user, global_usage):
        global_usage(CEILING - 2)
        user, _ = create_test_user(email="under@example.com")
        _check_screenshot_rate_limit(db, user.id, screenshot_count=1)  # no raise

    def test_at_ceiling_returns_503_and_debits_nothing(
        self, client, db, auth_headers, seed_scan_balance, global_usage, owner_alert
    ):
        global_usage(CEILING)
        headers, user = auth_headers(email="capped@example.com")
        seed_scan_balance(user.id, credits=3)

        with patch("app.services.screenshot_service.anthropic.Anthropic") as anthropic_ctor:
            response = client.post(
                "/screenshot/process",
                headers=headers,
                files={"file": _png_upload()},
                data={"save_workout": "false"},
            )

        assert response.status_code == 503, response.json()
        assert "no credit was consumed" in response.json()["detail"].lower()
        assert int(response.headers["Retry-After"]) > 0
        anthropic_ctor.assert_not_called()
        assert _balance(db, user.id).scan_credits == 3
        assert db.query(ScreenshotUsage).filter(ScreenshotUsage.user_id == user.id).count() == 0
        # Refused while the ceiling is hit — even though the user had credit.
        owner_alert.assert_called_once()
        assert "ceiling" in owner_alert.call_args.args[0].lower()

    def test_batch_counts_every_screenshot(
        self, client, db, auth_headers, seed_scan_balance, global_usage
    ):
        """8 used of 10: one more would pass, a batch of three must not —
        and unlimited users are refused too; the ceiling is about spend."""
        global_usage(CEILING - 2)
        headers, user = auth_headers(email="batch@example.com")
        seed_scan_balance(user.id, credits=50, has_unlimited=True)

        _check_screenshot_rate_limit(db, user.id, screenshot_count=2)  # exactly at cap: ok
        with pytest.raises(SpendCeilingExceeded):
            _check_screenshot_rate_limit(db, user.id, screenshot_count=3)

        with patch("app.services.screenshot_service.anthropic.Anthropic") as anthropic_ctor:
            response = client.post(
                "/screenshot/process/batch",
                headers=headers,
                files=[("files", _png_upload(f"{i}.png")) for i in range(3)],
                data={"save_workout": "false"},
            )
        assert response.status_code == 503, response.json()
        anthropic_ctor.assert_not_called()
        assert _balance(db, user.id).scan_credits == 50

    def test_ceiling_alert_fires_once_per_day(
        self, client, db, auth_headers, seed_scan_balance, global_usage, owner_alert
    ):
        global_usage(CEILING)
        headers, user = auth_headers(email="repeat@example.com")
        seed_scan_balance(user.id, credits=3)
        # Yesterday's alert must not suppress today's.
        screenshot_api._spend_alert_sent_on["ceiling"] = FIXED_NOW.date() - timedelta(days=1)

        for _ in range(3):
            response = client.post(
                "/screenshot/process",
                headers=headers,
                files={"file": _png_upload()},
                data={"save_workout": "false"},
            )
            assert response.status_code == 503

        assert owner_alert.call_count == 1
        assert screenshot_api._spend_alert_sent_on["ceiling"] == FIXED_NOW.date()

    def test_warn_threshold_alerts_before_cap(
        self, client, db, auth_headers, seed_scan_balance, global_usage, owner_alert, mock_anthropic
    ):
        """7 used of 10 with an 80% threshold: the next scan (8th) goes
        through, is billed as normal, and warns the owner — once."""
        global_usage(7)
        first_headers, first = auth_headers(email="warn-a@example.com")
        second_headers, second = auth_headers(email="warn-b@example.com")
        seed_scan_balance(first.id, credits=3)
        seed_scan_balance(second.id, credits=3)

        with patch(
            "app.services.screenshot_service.anthropic.Anthropic",
            mock_anthropic(MINIMAL_EXTRACTION),
        ):
            for headers in (first_headers, second_headers):
                response = client.post(
                    "/screenshot/process",
                    headers=headers,
                    files={"file": _png_upload()},
                    data={"save_workout": "false"},
                )
                assert response.status_code == 200, response.json()

        assert _balance(db, first.id).scan_credits == 2  # a warning is not a refusal
        assert _balance(db, second.id).scan_credits == 2
        assert owner_alert.call_count == 1
        subject = owner_alert.call_args.args[0].lower()
        assert "approaching" in subject and "reached" not in subject

    def test_refusal_is_the_generic_http_error_shape(self, db, create_test_user, global_usage):
        global_usage(CEILING)
        user, _ = create_test_user(email="shape@example.com")
        with pytest.raises(HTTPException) as exc_info:
            _check_screenshot_rate_limit(db, user.id, screenshot_count=1)
        assert exc_info.value.status_code == 503
        assert exc_info.value.headers["Retry-After"]


class TestPasswordResetIpLimit:
    @patch("app.api.password_reset.send_password_reset_email", return_value=True)
    def test_eleventh_request_from_one_ip_is_429(self, mock_email, client, create_test_user):
        """Ten different addresses in ten minutes pass; the eleventh is
        blocked — this is the spray shape the per-email cooldown cannot see."""
        for i in range(10):
            create_test_user(email=f"spray{i}@example.com")
            response = client.post(
                "/auth/password-reset/request", json={"email": f"spray{i}@example.com"}
            )
            assert response.status_code == 200, f"request {i + 1}: {response.status_code}"
        assert mock_email.call_count == 10

        blocked = client.post(
            "/auth/password-reset/request", json={"email": "spray-final@example.com"}
        )
        assert blocked.status_code == 429
        assert int(blocked.headers["Retry-After"]) > 0
        assert mock_email.call_count == 10
