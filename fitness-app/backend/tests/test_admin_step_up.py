"""Step-up password re-check for destructive admin actions (control-plane spec §4.5)."""
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core.admin_auth import require_admin, verify_step_up
from app.core.config import settings
from app.core.security import create_admin_token
from tests.helpers_admin import make_request


class TestVerifyStepUp:
    def test_correct_password_passes_and_resets_counter(self, db, admin_user):
        user, pwd = admin_user(email="step-ok@example.com")
        user.admin_failed_logins = 2
        db.commit()
        verify_step_up(db, user, pwd)
        db.refresh(user)
        assert user.admin_failed_logins == 0

    def test_missing_password_401(self, db, admin_user):
        user, _ = admin_user(email="step-missing@example.com")
        with pytest.raises(HTTPException) as exc:
            verify_step_up(db, user, None)
        assert exc.value.status_code == 401

    def test_wrong_password_401_and_counts(self, db, admin_user):
        user, _ = admin_user(email="step-wrong@example.com")
        with pytest.raises(HTTPException) as exc:
            verify_step_up(db, user, "nope")
        assert exc.value.status_code == 401
        db.refresh(user)
        assert user.admin_failed_logins == 1
        assert user.token_version == 0

    async def test_repeated_failures_revoke_the_session(self, db, admin_user, monkeypatch):
        user, _ = admin_user(email="step-revoke@example.com")
        monkeypatch.setattr(settings, "ADMIN_STEP_UP_FAILURES_TO_REVOKE", 3)
        token, _ = create_admin_token(user)
        creds = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=token,
        )
        assert (await require_admin(make_request("/admin/x", "POST"), creds, db)).id == user.id

        for _ in range(3):
            with pytest.raises(HTTPException):
                verify_step_up(db, user, "nope")
        db.refresh(user)
        assert user.token_version == 1
        assert user.admin_failed_logins == 0

        with pytest.raises(HTTPException) as exc:
            await require_admin(make_request("/admin/x", "POST"), creds, db)
        assert exc.value.status_code == 401
