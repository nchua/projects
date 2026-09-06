"""
Step-up password re-check for destructive admin actions (control-plane spec
§4.5, §16): the ``verify_step_up`` unit behaviour, then every destructive
route driven with a wrong password — parametrized over
``helpers_admin.DESTRUCTIVE`` so a new destructive route is covered the
moment it joins the registry.
"""
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core.admin_auth import require_admin, verify_step_up
from app.core.config import settings
from app.core.security import create_admin_token
from app.models.admin import AdminAuditLog
from tests.helpers_admin import CASES, DESTRUCTIVE, MutationContext, drive, make_request


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


def _audit_count(db) -> int:
    return db.query(AdminAuditLog).count()


def _ctx(db, admin_pair, password: str):
    headers, actor, target, _ = admin_pair("stepup")
    return headers, MutationContext(db=db, actor=actor, target=target, password=password)


@pytest.mark.parametrize("case", DESTRUCTIVE, ids=[c.name for c in DESTRUCTIVE])
def test_wrong_password_is_401_and_writes_no_audit_row(
    client, db, admin_pair, case
):
    headers, ctx = _ctx(db, admin_pair, password="not-the-password")
    before = _audit_count(db)
    response, _ = drive(client, headers, case, ctx)
    assert response.status_code == 401, (case.name, response.text)
    assert _audit_count(db) == before
    db.refresh(ctx.actor)
    assert ctx.actor.admin_failed_logins == 1


@pytest.mark.parametrize("case", DESTRUCTIVE, ids=[c.name for c in DESTRUCTIVE])
def test_missing_password_is_refused_without_an_audit_row(
    client, db, admin_pair, case
):
    """``StepUpBody`` routes 422 on the missing field; optional-password routes 401 in the service."""
    headers, ctx = _ctx(db, admin_pair, password="TestPass123!")
    before = _audit_count(db)
    call = case.build(ctx)
    call.json.pop("password", None)
    response = client.request(call.method, call.path, json=call.json, headers={**headers, **call.headers})
    assert response.status_code in (401, 422), (case.name, response.text)
    assert _audit_count(db) == before


def test_five_failures_revoke_the_session_and_a_success_resets_the_counter(
    client, db, admin_pair, monkeypatch
):
    monkeypatch.setattr(settings, "ADMIN_STEP_UP_FAILURES_TO_REVOKE", 5)
    headers, ctx = _ctx(db, admin_pair, password="TestPass123!")
    wrong = MutationContext(db=db, actor=ctx.actor, target=ctx.target, password="wrong", tag=ctx.tag)
    version = ctx.actor.token_version

    for _ in range(4):
        assert drive(client, headers, CASES["soft_delete"], wrong)[0].status_code == 401
    db.refresh(ctx.actor)
    assert ctx.actor.admin_failed_logins == 4

    ok, _ = drive(client, headers, CASES["credits_large"], ctx)  # a correct password
    assert ok.status_code == 200, ok.text
    db.refresh(ctx.actor)
    assert ctx.actor.admin_failed_logins == 0
    assert ctx.actor.token_version == version

    for _ in range(5):
        assert drive(client, headers, CASES["soft_delete"], wrong)[0].status_code == 401
    db.refresh(ctx.actor)
    assert ctx.actor.token_version == version + 1
    assert ctx.actor.admin_failed_logins == 0
    assert client.get("/admin/me", headers=headers).status_code == 401  # the session died
