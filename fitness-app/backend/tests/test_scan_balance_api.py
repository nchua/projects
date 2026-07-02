"""
Tests for the /scan-balance API (screenshot scanner monetization).

Covers:
- GET /scan-balance lazy-creates a balance with the free monthly credits
- POST /scan-balance/verify-purchase: crediting, App Store retry idempotency
  (duplicate transaction_id), unknown product rejection, unlimited product
- POST /scan-balance/restore-purchases re-flags has_unlimited from an
  existing PurchaseRecord
- Monthly free-scan reset: expired free_scans_reset_at re-credits
  FREE_MONTHLY_SCANS and advances the reset date in 30-day steps past now,
  both on GET /scan-balance and inside the /screenshot/process credit
  reservation (_apply_monthly_reset_if_needed).
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.api.scan_balance import PRODUCT_CREDITS, UNLIMITED_PRODUCT_ID
from app.core.config import settings
from app.models.scan_balance import PurchaseRecord, ScanBalance

SCAN_20_PRODUCT_ID = "com.nickchua.fitnessapp.scan_20"


def _parse_utc(value: str) -> datetime:
    """Parse an API datetime; SQLite round-trips drop tzinfo, so assume UTC."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class TestGetScanBalance:
    def test_fresh_user_gets_default_balance(self, client, auth_headers):
        headers, user = auth_headers(email="fresh-balance@example.com")

        response = client.get("/scan-balance", headers=headers)

        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body.keys()) == {"scan_credits", "has_unlimited", "free_scans_reset_at"}
        assert body["scan_credits"] == settings.FREE_MONTHLY_SCANS
        assert body["has_unlimited"] is False

        # Reset date is ~30 days out
        reset_at = _parse_utc(body["free_scans_reset_at"])
        now = datetime.now(timezone.utc)
        assert now + timedelta(days=29) < reset_at <= now + timedelta(days=31)


class TestVerifyPurchase:
    def test_known_product_adds_credits(self, client, auth_headers):
        headers, user = auth_headers(email="buy-scan20@example.com")

        response = client.post(
            "/scan-balance/verify-purchase",
            headers=headers,
            json={"transaction_id": "txn-scan20-1", "product_id": SCAN_20_PRODUCT_ID},
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["success"] is True
        assert body["credits_added"] == PRODUCT_CREDITS[SCAN_20_PRODUCT_ID]
        assert body["new_balance"] == settings.FREE_MONTHLY_SCANS + PRODUCT_CREDITS[SCAN_20_PRODUCT_ID]
        assert body["has_unlimited"] is False

    def test_duplicate_transaction_id_does_not_double_credit(self, client, auth_headers):
        """App Store retries replay the same transaction_id — the second call
        must be a no-op (credits_added=0, balance unchanged)."""
        headers, user = auth_headers(email="retry-txn@example.com")
        payload = {"transaction_id": "txn-retry-1", "product_id": SCAN_20_PRODUCT_ID}

        first = client.post("/scan-balance/verify-purchase", headers=headers, json=payload)
        assert first.status_code == 200
        balance_after_first = first.json()["new_balance"]

        second = client.post("/scan-balance/verify-purchase", headers=headers, json=payload)
        assert second.status_code == 200
        body = second.json()
        assert body["success"] is True
        assert body["credits_added"] == 0
        assert body["new_balance"] == balance_after_first

    def test_unknown_product_id_returns_400(self, client, auth_headers):
        headers, user = auth_headers(email="bogus-product@example.com")

        response = client.post(
            "/scan-balance/verify-purchase",
            headers=headers,
            json={"transaction_id": "txn-bogus-1", "product_id": "com.bogus.not_a_product"},
        )

        assert response.status_code == 400
        assert "Unknown product_id" in response.json()["detail"]

    def test_unlimited_product_sets_flag_without_adding_credits(self, client, auth_headers):
        headers, user = auth_headers(email="buy-unlimited@example.com")

        response = client.post(
            "/scan-balance/verify-purchase",
            headers=headers,
            json={"transaction_id": "txn-unlimited-1", "product_id": UNLIMITED_PRODUCT_ID},
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["success"] is True
        assert body["credits_added"] == 0
        assert body["has_unlimited"] is True
        # Free credits untouched
        assert body["new_balance"] == settings.FREE_MONTHLY_SCANS


class TestRestorePurchases:
    def test_restore_reflags_unlimited_from_existing_record(
        self, client, db, auth_headers, seed_scan_balance
    ):
        """User reinstalls the app: balance row lost its flag but the
        PurchaseRecord survives — restore must re-flag has_unlimited."""
        headers, user = auth_headers(email="restore-unlimited@example.com")
        seed_scan_balance(user.id, credits=0, has_unlimited=False)
        db.add(PurchaseRecord(
            user_id=user.id,
            product_id=UNLIMITED_PRODUCT_ID,
            transaction_id=f"txn-restore-{uuid.uuid4().hex[:8]}",
            credits_added=0,
            purchase_type="non_consumable",
        ))
        db.commit()

        response = client.post("/scan-balance/restore-purchases", headers=headers)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["has_unlimited"] is True
        assert body["scan_credits"] == 0  # restore adds no credits

        # Persisted, not just echoed
        db.expire_all()
        balance = db.query(ScanBalance).filter(ScanBalance.user_id == user.id).first()
        assert balance.has_unlimited is True


class TestMonthlyFreeScanReset:
    def test_expired_reset_recredits_and_advances_date_in_30_day_steps(
        self, client, auth_headers, seed_scan_balance
    ):
        headers, user = auth_headers(email="reset-due@example.com")
        original_reset = (
            datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=65)
        )
        seed_scan_balance(user.id, credits=0, free_scans_reset_at=original_reset)

        response = client.get("/scan-balance", headers=headers)

        assert response.status_code == 200, response.text
        body = response.json()
        # Exactly one re-credit, even though two 30-day periods elapsed
        assert body["scan_credits"] == settings.FREE_MONTHLY_SCANS

        # Reset date advanced in 30-day steps until it passed now:
        # -65d -> -35d -> -5d -> +25d (3 steps of 30 days)
        new_reset = _parse_utc(body["free_scans_reset_at"])
        assert new_reset > datetime.now(timezone.utc)
        assert new_reset - original_reset == timedelta(days=90)

    def test_zero_credit_user_with_expired_reset_can_scan_again(
        self, client, db, auth_headers, seed_scan_balance, mock_anthropic,
        png_bytes, anthropic_api_key
    ):
        """_apply_monthly_reset_if_needed runs inside the credit reservation,
        so a 0-credit user whose reset elapsed can scan without first
        touching GET /scan-balance."""
        headers, user = auth_headers(email="reset-scan@example.com")
        seed_scan_balance(
            user.id,
            credits=0,
            free_scans_reset_at=datetime.now(timezone.utc) - timedelta(days=1),
        )

        mock_ctor = mock_anthropic({"screenshot_type": "gym_workout", "exercises": []})
        with patch("app.services.screenshot_service.anthropic.Anthropic", mock_ctor):
            response = client.post(
                "/screenshot/process",
                headers=headers,
                files={"file": ("shot.png", png_bytes, "image/png")},
                data={"save_workout": "false"},
            )

        assert response.status_code == 200, response.text

        # Reset credited FREE_MONTHLY_SCANS, then the scan consumed 1
        db.expire_all()
        balance = db.query(ScanBalance).filter(ScanBalance.user_id == user.id).first()
        assert balance.scan_credits == settings.FREE_MONTHLY_SCANS - 1
