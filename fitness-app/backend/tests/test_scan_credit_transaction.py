"""
Tests for atomic scan-credit deduction, Anthropic timeout handling, and the
prompt-injection allowlist on `matched_exercise_id`.

See PR C — Monetization correctness.

NOTE: SQLite does not implement true row-level `FOR UPDATE` locks, so these
tests assert *ordering and correctness under the existing transaction model*.
Real row-lock behaviour is verified against Postgres in CI (PR B).
"""
import io
import json
import os
import threading
from unittest.mock import MagicMock, patch

import anthropic

# Ensure downstream imports see an API key; the real client is mocked below.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.api.screenshot import _reserve_scan_credits
from app.models.exercise import Exercise
from app.models.scan_balance import ScanBalance

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_png_bytes() -> bytes:
    """Return a minimal valid PNG (1x1 transparent pixel)."""
    # 67-byte PNG: signature + IHDR + IDAT + IEND
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000d49444154789c636000010000000500010d0a2db40000000049454e"
        "44ae426082"
    )


def _mock_claude_response(payload: dict) -> MagicMock:
    """Mock anthropic Message response returning the given JSON payload."""
    block = MagicMock()
    block.text = json.dumps(payload)
    message = MagicMock()
    message.content = [block]
    return message


def _seed_balance(db, user_id: str, credits: int, has_unlimited: bool = False):
    balance = ScanBalance(
        user_id=user_id,
        scan_credits=credits,
        has_unlimited=has_unlimited,
    )
    db.add(balance)
    db.commit()
    db.refresh(balance)
    return balance


def _seed_exercise(db, name: str, user_id=None, is_custom: bool = False) -> Exercise:
    ex = Exercise(
        name=name,
        category="compound",
        primary_muscle="chest",
        is_custom=is_custom,
        user_id=user_id,
    )
    db.add(ex)
    db.commit()
    db.refresh(ex)
    return ex


# ---------------------------------------------------------------------------
# _reserve_scan_credits unit behaviour (no HTTP)
# ---------------------------------------------------------------------------

class TestReserveScanCredits:
    def test_reserve_success_deducts(self, db, create_test_user):
        user, _ = create_test_user(email="reserve1@example.com")
        _seed_balance(db, user.id, credits=3)

        ok = _reserve_scan_credits(db, user.id, count=1)
        assert ok is True

        db.commit()
        balance = db.query(ScanBalance).filter(ScanBalance.user_id == user.id).first()
        assert balance.scan_credits == 2

    def test_reserve_insufficient_returns_false(self, db, create_test_user):
        user, _ = create_test_user(email="reserve2@example.com")
        _seed_balance(db, user.id, credits=0)

        ok = _reserve_scan_credits(db, user.id, count=1)
        assert ok is False

        db.rollback()
        balance = db.query(ScanBalance).filter(ScanBalance.user_id == user.id).first()
        assert balance.scan_credits == 0

    def test_reserve_unlimited_no_deduction(self, db, create_test_user):
        user, _ = create_test_user(email="reserve3@example.com")
        _seed_balance(db, user.id, credits=0, has_unlimited=True)

        ok = _reserve_scan_credits(db, user.id, count=5)
        assert ok is True

        db.commit()
        balance = db.query(ScanBalance).filter(ScanBalance.user_id == user.id).first()
        assert balance.scan_credits == 0  # untouched because unlimited
        assert balance.has_unlimited is True

    def test_rollback_restores_credits(self, db, create_test_user):
        """If the caller rolls back after reservation, credits come back."""
        user, _ = create_test_user(email="reserve4@example.com")
        _seed_balance(db, user.id, credits=2)

        ok = _reserve_scan_credits(db, user.id, count=1)
        assert ok is True

        # Simulate a failure downstream → rollback
        db.rollback()

        balance = db.query(ScanBalance).filter(ScanBalance.user_id == user.id).first()
        assert balance.scan_credits == 2  # deduction was rolled back


# ---------------------------------------------------------------------------
# End-to-end: atomic credit race via POST /screenshot/process
# ---------------------------------------------------------------------------

class TestScreenshotCreditRace:
    def test_concurrent_single_requests_one_succeeds_one_402(self, client, auth_headers, db):
        """
        Two near-simultaneous POSTs against a user with 1 credit must yield
        exactly one 200 and one 402. Final balance is 0 — never negative.

        We bypass the 10-second cooldown (a separate rate-limit layer) to
        exercise the *credit* race-condition boundary specifically. True
        row-lock behaviour is verified against Postgres in PR B's CI job;
        on SQLite this test still asserts the correct invariant.
        """
        headers, user = auth_headers(email="race@example.com")
        _seed_balance(db, user.id, credits=1)

        mock_msg = _mock_claude_response({
            "screenshot_type": "gym_workout",
            "session_date": "2026-04-19",
            "session_name": "Test",
            "duration_minutes": 30,
            "summary": {"tonnage_lb": 500, "total_reps": 10},
            "exercises": [],
        })
        png = _make_png_bytes()
        results = []
        results_lock = threading.Lock()

        # Bypass cooldown: we're specifically testing credit atomicity, not
        # the throttle. The `_check_screenshot_rate_limit` function still
        # validates the feature flag and daily cap.
        with patch("app.api.screenshot.COOLDOWN_SECONDS", 0), \
             patch("app.services.screenshot_service.anthropic.Anthropic") as MockClient:
            instance = MagicMock()
            instance.messages.create.return_value = mock_msg
            MockClient.return_value = instance

            def _call():
                resp = client.post(
                    "/screenshot/process",
                    headers=headers,
                    files={"file": ("shot.png", io.BytesIO(png), "image/png")},
                    data={"save_workout": "false"},
                )
                with results_lock:
                    results.append(resp.status_code)

            t1 = threading.Thread(target=_call)
            t2 = threading.Thread(target=_call)
            t1.start()
            t2.start()
            t1.join()
            t2.join()

        assert sorted(results) == [200, 402], f"Got statuses {results}"

        db.expire_all()
        balance = db.query(ScanBalance).filter(ScanBalance.user_id == user.id).first()
        assert balance.scan_credits == 0, f"Expected 0 credits remaining, got {balance.scan_credits}"

    def test_second_request_after_exhaustion_is_402(self, client, auth_headers, db):
        """Sequential: first succeeds, second (0 credits) gets 402."""
        headers, user = auth_headers(email="exhaust@example.com")
        _seed_balance(db, user.id, credits=1)

        mock_msg = _mock_claude_response({
            "screenshot_type": "gym_workout",
            "exercises": [],
        })
        png = _make_png_bytes()

        with patch("app.services.screenshot_service.anthropic.Anthropic") as MockClient:
            instance = MagicMock()
            instance.messages.create.return_value = mock_msg
            MockClient.return_value = instance

            first = client.post(
                "/screenshot/process",
                headers=headers,
                files={"file": ("a.png", io.BytesIO(png), "image/png")},
                data={"save_workout": "false"},
            )
            assert first.status_code == 200, first.json()

            # Second call — hit 10s cooldown? bypass by pushing last usage
            # back. Simpler: wait via patching out the cooldown check is
            # tricky, so we bypass by deleting the usage row.
            from app.models.screenshot_usage import ScreenshotUsage
            db.query(ScreenshotUsage).delete()
            db.commit()

            second = client.post(
                "/screenshot/process",
                headers=headers,
                files={"file": ("b.png", io.BytesIO(png), "image/png")},
                data={"save_workout": "false"},
            )
            assert second.status_code == 402, second.json()


# ---------------------------------------------------------------------------
# Anthropic timeout → 504 and no credit consumed
# ---------------------------------------------------------------------------

class TestAnthropicTimeoutBehaviour:
    def test_timeout_returns_504_and_preserves_credit(self, client, auth_headers, db):
        headers, user = auth_headers(email="timeout@example.com")
        _seed_balance(db, user.id, credits=2)

        png = _make_png_bytes()

        with patch("app.services.screenshot_service.anthropic.Anthropic") as MockClient:
            instance = MagicMock()
            # Raise APITimeoutError the way the SDK would.
            instance.messages.create.side_effect = anthropic.APITimeoutError(
                request=MagicMock()
            )
            MockClient.return_value = instance

            resp = client.post(
                "/screenshot/process",
                headers=headers,
                files={"file": ("slow.png", io.BytesIO(png), "image/png")},
                data={"save_workout": "false"},
            )

        assert resp.status_code == 504, resp.json()
        assert "timed out" in resp.json()["detail"].lower()

        db.expire_all()
        balance = db.query(ScanBalance).filter(ScanBalance.user_id == user.id).first()
        assert balance.scan_credits == 2, (
            f"Timed-out call should NOT consume a credit; got {balance.scan_credits}"
        )


# ---------------------------------------------------------------------------
# Prompt-injection allowlist
# ---------------------------------------------------------------------------

class TestPromptInjectionAllowlist:
    def test_other_users_exercise_id_is_dropped(self, client, auth_headers, create_test_user, db):
        """
        If Claude returns a `matched_exercise_id` belonging to a different
        user's custom exercise, the ID must be stripped (set to None) and
        extraction still succeeds.
        """
        headers, user = auth_headers(email="victim@example.com")
        # A second user owns a custom exercise we must NOT leak.
        other_user, _ = create_test_user(email="attacker@example.com")

        _seed_balance(db, user.id, credits=3)

        # Seed one library exercise that the fuzzy matcher CAN legitimately
        # pick, and a second user's custom exercise that must be rejected.
        library_ex = _seed_exercise(db, "Barbell Bench Press", user_id=None, is_custom=False)
        other_custom = _seed_exercise(
            db, "Secret Lift", user_id=other_user.id, is_custom=True
        )

        # Claude is tricked into returning the other user's exercise id.
        mock_msg = _mock_claude_response({
            "screenshot_type": "gym_workout",
            "exercises": [
                {
                    "name": "Bench Press",
                    "matched_exercise_id": other_custom.id,
                    "sets": [{"weight_lb": 135, "reps": 10, "sets": 1, "is_warmup": False}],
                }
            ],
        })
        png = _make_png_bytes()

        with patch("app.services.screenshot_service.anthropic.Anthropic") as MockClient:
            instance = MagicMock()
            instance.messages.create.return_value = mock_msg
            MockClient.return_value = instance

            resp = client.post(
                "/screenshot/process",
                headers=headers,
                files={"file": ("shot.png", io.BytesIO(png), "image/png")},
                data={"save_workout": "false"},
            )

        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert body["exercises"], "Extraction should still return exercise rows"

        ex0 = body["exercises"][0]
        # The attacker-supplied id must be gone.
        assert ex0["matched_exercise_id"] != other_custom.id, (
            "Other user's custom exercise id leaked through the response!"
        )
        # Fuzzy matcher may have matched the library bench press — that's
        # fine and is explicitly allowed. What matters is no cross-tenant leak.
        if ex0["matched_exercise_id"] is not None:
            assert ex0["matched_exercise_id"] == library_ex.id
