"""
Admin identity, token classes, token_version, bootstrap, and admin sessions
(control-plane spec §4).
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core import admin_bootstrap
from app.core.admin_auth import require_admin
from app.core.admin_bootstrap import bootstrap_admin, run_startup_tasks
from app.core.config import settings
from app.core.security import (
    ADMIN_AUDIENCE,
    create_access_token,
    create_admin_token,
    decode_admin_token,
    decode_token,
    user_token_claims,
)
from app.models.admin import AdminAuditLog
from app.models.password_reset import PasswordResetToken
from app.models.user import User
from app.services.admin_session_service import mint_admin_session
from tests.helpers_admin import make_request


async def _call_require_admin(db, token: str) -> User:
    creds = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=token,
    )
    return await require_admin(make_request(), creds, db)


class TestTokenClasses:
    def test_admin_token_round_trips(self, db, admin_user):
        user, _ = admin_user(email="tok-admin@example.com")
        token, expires = create_admin_token(user)
        payload = decode_admin_token(token)
        assert payload["sub"] == user.id
        assert payload["type"] == "admin"
        assert payload["aud"] == ADMIN_AUDIENCE
        assert payload["ver"] == 0
        assert expires > datetime.now(timezone.utc)
        assert expires <= datetime.now(timezone.utc) + timedelta(
            minutes=settings.ADMIN_TOKEN_EXPIRE_MINUTES
        )

    def test_admin_token_rejected_by_user_decoder(self, db, admin_user):
        user, _ = admin_user(email="tok-admin2@example.com")
        token, _ = create_admin_token(user)
        assert decode_token(token) is None

    def test_access_token_rejected_by_admin_decoder(self, create_test_user):
        user, _ = create_test_user(email="tok-user@example.com")
        assert decode_admin_token(create_access_token(data=user_token_claims(user))) is None

    def test_admin_token_on_user_route_is_401(self, client, admin_user):
        user, _ = admin_user(email="tok-route@example.com")
        token, _ = create_admin_token(user)
        response = client.get("/profile", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    async def test_require_admin_accepts_admin(self, db, admin_user):
        user, _ = admin_user(email="req-ok@example.com")
        token, _ = create_admin_token(user)
        actor = await _call_require_admin(db, token)
        assert actor.id == user.id

    async def test_require_admin_rejects_access_token(self, db, admin_user):
        user, _ = admin_user(email="req-access@example.com")
        with pytest.raises(HTTPException) as exc:
            await _call_require_admin(db, create_access_token(data=user_token_claims(user)))
        assert exc.value.status_code == 401

    async def test_require_admin_403_when_flag_flipped_mid_session(self, db, admin_user):
        user, _ = admin_user(email="req-flip@example.com")
        token, _ = create_admin_token(user)
        user.is_admin = False
        db.commit()
        with pytest.raises(HTTPException) as exc:
            await _call_require_admin(db, token)
        assert exc.value.status_code == 403

    async def test_require_admin_401_on_version_bump(self, db, admin_user):
        user, _ = admin_user(email="req-ver@example.com")
        token, _ = create_admin_token(user)
        user.token_version += 1
        db.commit()
        with pytest.raises(HTTPException) as exc:
            await _call_require_admin(db, token)
        assert exc.value.status_code == 401

    async def test_require_admin_401_for_deleted(self, db, admin_user):
        user, _ = admin_user(email="req-del@example.com")
        token, _ = create_admin_token(user)
        user.is_deleted = True
        db.commit()
        with pytest.raises(HTTPException) as exc:
            await _call_require_admin(db, token)
        assert exc.value.status_code == 401

    async def test_require_admin_401_for_garbage(self, db):
        with pytest.raises(HTTPException) as exc:
            await _call_require_admin(db, "not-a-token")
        assert exc.value.status_code == 401


class TestTokenVersion:
    def test_bump_revokes_access_token(self, client, db, auth_headers):
        headers, user = auth_headers(email="ver-access@example.com")
        assert client.get("/profile", headers=headers).status_code == 200
        user.token_version += 1
        db.commit()
        assert client.get("/profile", headers=headers).status_code == 401

    def test_bump_revokes_refresh_token(self, client, db, create_test_user):
        user, pwd = create_test_user(email="ver-refresh@example.com")
        login = client.post("/auth/login", json={"email": user.email, "password": pwd})
        refresh = login.json()["refresh_token"]
        assert client.post("/auth/refresh", json={"refresh_token": refresh}).status_code == 200
        user.token_version += 1
        db.commit()
        response = client.post("/auth/refresh", json={"refresh_token": refresh})
        assert response.status_code == 401

    def test_legacy_token_without_ver_is_version_zero(self, client, create_test_user):
        user, _ = create_test_user(email="ver-legacy@example.com")
        claims = {"sub": user.id}  # legacy shape: no ``ver`` claim
        token = create_access_token(data=claims)
        response = client.get("/profile", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200

    def test_password_reset_bumps_version(self, client, db, create_test_user):
        user, _ = create_test_user(email="ver-reset@example.com")
        db.add(
            PasswordResetToken(
                user_id=user.id,
                email=user.email,
                code="123456",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            )
        )
        db.commit()
        response = client.post(
            "/auth/password-reset/verify",
            json={"email": user.email, "code": "123456", "new_password": "NewPass123!"},
        )
        assert response.status_code == 200, response.text
        db.refresh(user)
        assert user.token_version == 1


class TestMassAssignment:
    def test_register_ignores_is_admin(self, client, db):
        response = client.post(
            "/auth/register",
            json={"email": "mass-reg@example.com", "password": "TestPass123!", "is_admin": True},
        )
        assert response.status_code == 201, response.text
        user = db.query(User).filter(User.email == "mass-reg@example.com").one()
        assert user.is_admin is False

    def test_profile_update_ignores_is_admin(self, client, db, auth_headers):
        headers, user = auth_headers(email="mass-profile@example.com")
        response = client.put("/profile", headers=headers, json={"age": 30, "is_admin": True})
        assert response.status_code == 200, response.text
        db.refresh(user)
        assert user.is_admin is False

    def test_username_update_ignores_is_admin(self, client, db, auth_headers):
        headers, user = auth_headers(email="mass-username@example.com")
        response = client.put(
            "/users/username", headers=headers, json={"username": "massuser", "is_admin": True}
        )
        assert response.status_code == 200, response.text
        db.refresh(user)
        assert user.is_admin is False


class TestBootstrap:
    def test_promotes_matching_account_case_insensitively_and_audits(
        self, db, create_test_user, monkeypatch
    ):
        user, _ = create_test_user(email="Owner-Boot@example.com")
        monkeypatch.setattr(settings, "ADMIN_BOOTSTRAP_EMAIL", "owner-boot@example.com")

        assert bootstrap_admin(db) == user.id
        db.refresh(user)
        assert user.is_admin is True
        row = (
            db.query(AdminAuditLog)
            .filter(AdminAuditLog.action == "admin.bootstrap", AdminAuditLog.target_id == user.id)
            .one()
        )
        assert row.actor_user_id is None
        assert row.after == {"is_admin": True}

        # Idempotent: a second boot changes nothing and writes nothing.
        assert bootstrap_admin(db) is None
        assert db.query(AdminAuditLog).filter(AdminAuditLog.action == "admin.bootstrap").count() == 1

    def test_unset_variable_is_noop(self, db, monkeypatch):
        monkeypatch.setattr(settings, "ADMIN_BOOTSTRAP_EMAIL", "")
        assert bootstrap_admin(db) is None

    def test_no_match_promotes_nobody(self, db, create_test_user, monkeypatch):
        user, _ = create_test_user(email="boot-other@example.com")
        monkeypatch.setattr(settings, "ADMIN_BOOTSTRAP_EMAIL", "boot-typo@example.com")
        assert bootstrap_admin(db) is None
        assert db.query(User).filter(User.is_admin == True).count() == 0

    def test_deleted_account_not_promoted(self, db, create_test_user, monkeypatch):
        user, _ = create_test_user(email="boot-deleted@example.com")
        user.is_deleted = True
        db.commit()
        monkeypatch.setattr(settings, "ADMIN_BOOTSTRAP_EMAIL", user.email)
        assert bootstrap_admin(db) is None
        db.refresh(user)
        assert user.is_admin is False

    def test_case_collision_promotes_neither(self, db, create_test_user, monkeypatch):
        a, _ = create_test_user(email="collide@example.com")
        b, _ = create_test_user(email="Collide@example.com")
        monkeypatch.setattr(settings, "ADMIN_BOOTSTRAP_EMAIL", "COLLIDE@example.com")
        assert bootstrap_admin(db) is None
        db.refresh(a)
        db.refresh(b)
        assert a.is_admin is False and b.is_admin is False

    def test_run_startup_tasks_never_raises(self, monkeypatch):
        def _boom(_db):
            raise RuntimeError("db down")

        monkeypatch.setattr(admin_bootstrap, "bootstrap_admin", _boom)
        assert run_startup_tasks() is None


class TestMintAdminSession:
    def test_success_returns_admin_token_and_audits(self, db, admin_user):
        user, pwd = admin_user(email="mint-ok@example.com")
        token, expires_at = mint_admin_session(db, email=user.email, password=pwd)
        assert decode_admin_token(token)["sub"] == user.id
        row = (
            db.query(AdminAuditLog)
            .filter(AdminAuditLog.action == "session.create", AdminAuditLog.actor_user_id == user.id)
            .one()
        )
        assert row.target_id == user.id

    def test_bad_password_counts_then_locks(self, db, admin_user, monkeypatch):
        user, pwd = admin_user(email="mint-lock@example.com")
        monkeypatch.setattr(settings, "ADMIN_LOCKOUT_THRESHOLD", 3)
        for attempt in (1, 2):
            with pytest.raises(HTTPException) as exc:
                mint_admin_session(db, email=user.email, password="wrong")
            assert exc.value.status_code == 401
            db.refresh(user)
            assert user.admin_failed_logins == attempt
            assert user.admin_locked_until is None
        with pytest.raises(HTTPException) as exc:
            mint_admin_session(db, email=user.email, password="wrong")
        assert exc.value.status_code == 401
        db.refresh(user)
        assert user.admin_locked_until is not None
        assert user.admin_failed_logins == 0
        # Locked: even the right password is refused until the window passes.
        with pytest.raises(HTTPException) as exc:
            mint_admin_session(db, email=user.email, password=pwd)
        assert exc.value.status_code == 423
        assert "Retry-After" in exc.value.headers

    def test_success_resets_counter(self, db, admin_user):
        user, pwd = admin_user(email="mint-reset@example.com")
        with pytest.raises(HTTPException):
            mint_admin_session(db, email=user.email, password="wrong")
        mint_admin_session(db, email=user.email, password=pwd)
        db.refresh(user)
        assert user.admin_failed_logins == 0

    def test_non_admin_valid_password_is_403_and_does_not_count(self, db, create_test_user):
        user, pwd = create_test_user(email="mint-plain@example.com")
        with pytest.raises(HTTPException) as exc:
            mint_admin_session(db, email=user.email, password=pwd)
        assert exc.value.status_code == 403
        db.refresh(user)
        assert user.admin_failed_logins == 0

    def test_unknown_and_deleted_are_generic_401(self, db, admin_user):
        with pytest.raises(HTTPException) as exc:
            mint_admin_session(db, email="nobody@example.com", password="x")
        assert exc.value.status_code == 401
        user, pwd = admin_user(email="mint-deleted@example.com")
        user.is_deleted = True
        db.commit()
        with pytest.raises(HTTPException) as exc:
            mint_admin_session(db, email=user.email, password=pwd)
        assert exc.value.status_code == 401


class TestRequireAdminEdges:
    async def test_missing_header_is_401_not_403(self, db):
        with pytest.raises(HTTPException) as exc:
            await require_admin(make_request(), None, db)
        assert exc.value.status_code == 401
        assert exc.value.headers["WWW-Authenticate"] == "Bearer"


    async def test_expired_admin_token_is_401(self, db, admin_user, monkeypatch):
        user, _ = admin_user(email="req-expired@example.com")
        monkeypatch.setattr(settings, "ADMIN_TOKEN_EXPIRE_MINUTES", -1)
        token, _ = create_admin_token(user)
        assert decode_admin_token(token) is None
        with pytest.raises(HTTPException) as exc:
            await _call_require_admin(db, token)
        assert exc.value.status_code == 401
