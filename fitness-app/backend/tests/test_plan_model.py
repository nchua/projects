"""
The derived plan and status models (console v2 spec §3, §6.1, §7.2):
``plan_for`` on every §3.1 case, ``plans_for`` in three queries, ``status_for``
at the ``inactive_after_days`` / ``PURGE_GRACE_DAYS`` boundaries, and
``last_active_of`` precedence.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import event

from app.models.scan_balance import ScanBalance
from app.models.user import User
from app.services import entitlement_service as es
from app.services import settings_service
from app.services.admin_read_service import (
    StatusThresholds,
    last_active_of,
    status_for,
    status_thresholds,
)
from tests.helpers_admin import grant_admin

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
THRESHOLDS = StatusThresholds(inactive_after_days=30, grace_days=30)


@pytest.fixture
def user(db, create_test_user):
    u, _ = create_test_user(email=f"plan-{uuid.uuid4().hex[:8]}@example.com")
    return u


def _balance(db, user_id: str, credits: int) -> None:
    db.add(ScanBalance(user_id=user_id, scan_credits=credits, has_unlimited=False))
    db.commit()


class TestPlanFor:
    def test_no_rows_is_free_with_no_balance(self, db, user):
        plan = es.plan_for(db, user.id)
        default_free = int(settings_service.get(db, "FREE_MONTHLY_SCANS"))
        assert plan == es.Plan(
            plan="free", plan_source=None, expires_at=None, scan_credits=None,
            purchased_credits=0, free_monthly=default_free, override_keys=(),
        )

    def test_credits_at_or_below_free_is_free(self, db, user):
        free = int(settings_service.get(db, "FREE_MONTHLY_SCANS"))
        _balance(db, user.id, free)
        plan = es.plan_for(db, user.id)
        assert plan.plan == "free" and plan.scan_credits == free and plan.purchased_credits == 0

    def test_credits_above_free_is_credits(self, db, user):
        free = int(settings_service.get(db, "FREE_MONTHLY_SCANS"))
        _balance(db, user.id, free + 17)
        plan = es.plan_for(db, user.id)
        assert plan.plan == "credits" and plan.purchased_credits == 17 and plan.plan_source is None

    def test_active_override_is_override_even_with_purchased_credits(self, db, user):
        _balance(db, user.id, 40)
        grant_admin(db, user.id, es.KEY_DAILY_LIMIT, 5)
        db.commit()
        plan = es.plan_for(db, user.id)
        assert plan.plan == "override" and plan.override_keys == (es.KEY_DAILY_LIMIT,)
        assert plan.purchased_credits == 40 - plan.free_monthly

    def test_unlimited_beats_override_and_carries_source(self, db, user):
        grant_admin(db, user.id, es.KEY_COOLDOWN, 0)
        row = grant_admin(db, user.id, es.KEY_UNLIMITED, True)
        db.commit()
        plan = es.plan_for(db, user.id)
        assert plan.plan == "unlimited" and plan.plan_source == "admin_grant"
        assert plan.override_keys == (es.KEY_COOLDOWN,)  # the cap still shows as a secondary line
        assert plan.expires_at is None
        es.revoke(db, row)
        db.commit()
        assert es.plan_for(db, user.id).plan == "override"

    def test_purchase_sourced_unlimited_reads_purchase(self, db, user):
        es.grant(db, user_id=user.id, key=es.KEY_UNLIMITED, value=True, source="backfill")
        db.commit()
        assert es.plan_for(db, user.id).plan_source == "backfill"
        es.grant(db, user_id=user.id, key=es.KEY_UNLIMITED, value=True, source="purchase",
                 purchase_record_id=f"rec-{uuid.uuid4().hex[:6]}")
        db.commit()
        assert es.plan_for(db, user.id).plan_source == "purchase"  # the newest active row decides

    def test_expired_unlimited_falls_back_to_the_underlying_plan(self, db, user):
        _balance(db, user.id, 50)
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        es.grant(db, user_id=user.id, key=es.KEY_UNLIMITED, value=True, source="admin_grant",
                 expires_at=expires)
        db.commit()
        live = es.plan_for(db, user.id)
        assert live.plan == "unlimited" and live.expires_at is not None
        assert live.expires_at.replace(microsecond=0) == expires.replace(microsecond=0)
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        es.grant(db, user_id=user.id, key=es.KEY_UNLIMITED, value=True, source="admin_grant",
                 expires_at=past)  # newer but expired → not active
        for row in es.list_entitlements(db, user.id):
            row.expires_at = past
        db.commit()
        plan = es.plan_for(db, user.id)
        assert plan.plan == "credits" and plan.plan_source is None and plan.expires_at is None

    def test_purchased_credits_uses_the_per_user_free_monthly(self, db, user):
        _balance(db, user.id, 15)
        grant_admin(db, user.id, es.KEY_FREE_MONTHLY, 10)
        db.commit()
        plan = es.plan_for(db, user.id)
        assert plan.free_monthly == 10 and plan.purchased_credits == 5
        assert plan.plan == "override" and plan.override_keys == (es.KEY_FREE_MONTHLY,)

    def test_console_free_monthly_row_moves_the_threshold(self, db, user):
        _balance(db, user.id, 8)
        assert es.plan_for(db, user.id).plan == "credits"
        settings_service.set_value(db, "FREE_MONTHLY_SCANS", 8, updated_by=None)
        db.commit()
        plan = es.plan_for(db, user.id)
        assert plan.plan == "free" and plan.free_monthly == 8 and plan.purchased_credits == 0

    def test_snapshot_is_json_safe(self, db, user):
        grant_admin(db, user.id, es.KEY_UNLIMITED, True)
        db.commit()
        snap = es.plan_snapshot(es.plan_for(db, user.id))
        assert set(snap) == {
            "plan", "plan_source", "expires_at", "scan_credits", "purchased_credits",
            "free_monthly", "override_keys",
        }
        assert snap["override_keys"] == [] and snap["plan"] == "unlimited"


class TestPlansFor:
    def test_three_queries_for_a_page_and_unknown_ids_are_free(self, db, create_test_user):
        users = [create_test_user(email=f"page-{uuid.uuid4().hex[:8]}@example.com")[0] for _ in range(6)]
        _balance(db, users[0].id, 40)
        grant_admin(db, users[1].id, es.KEY_UNLIMITED, True)
        grant_admin(db, users[2].id, es.KEY_DAILY_LIMIT, 2)
        db.commit()

        ids = [u.id for u in users] + ["no-such-user"]  # loaded before counting (commit expired them)
        statements = []
        engine = db.get_bind().engine

        def listener(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        event.listen(engine, "before_cursor_execute", listener)
        try:
            plans = es.plans_for(db, ids)
        finally:
            event.remove(engine, "before_cursor_execute", listener)

        assert len(statements) == 3, statements  # entitlements, balances, the free-monthly setting
        assert plans[users[0].id].plan == "credits"
        assert plans[users[1].id].plan == "unlimited"
        assert plans[users[2].id].plan == "override"
        assert all(plans[u.id].plan == "free" for u in users[3:])
        assert plans["no-such-user"].plan == "free"

    def test_empty_page(self, db):
        assert es.plans_for(db, []) == {}


def _user(**fields) -> User:
    user = User(email="x@example.com", password_hash="h", is_deleted=False, is_admin=False)
    for name, value in fields.items():
        setattr(user, name, value)
    return user


class TestStatusFor:
    @pytest.mark.parametrize(
        "days_ago,expected",
        [(0, "active"), (29, "active"), (30, "active"), (31, "inactive"), (400, "inactive")],
    )
    def test_inactive_boundary(self, days_ago, expected):
        last_active = NOW.date() - timedelta(days=days_ago)
        assert status_for(_user(), last_active, NOW, THRESHOLDS) == expected

    def test_never_active_is_inactive(self):
        assert status_for(_user(), None, NOW, THRESHOLDS) == "inactive"

    @pytest.mark.parametrize(
        "days_ago,expected",
        [(0, "deleted"), (29, "deleted"), (30, "purge_eligible"), (31, "purge_eligible")],
    )
    def test_grace_boundary(self, days_ago, expected):
        user = _user(is_deleted=True, deleted_at=(NOW - timedelta(days=days_ago)).replace(tzinfo=None))
        assert status_for(user, NOW.date(), NOW, THRESHOLDS) == expected

    def test_deleted_without_timestamp_is_deleted(self):
        assert status_for(_user(is_deleted=True, deleted_at=None), None, NOW, THRESHOLDS) == "deleted"

    def test_admins_are_never_purge_eligible(self):
        user = _user(is_deleted=True, is_admin=True, deleted_at=(NOW - timedelta(days=90)).replace(tzinfo=None))
        assert status_for(user, None, NOW, THRESHOLDS) == "deleted"

    def test_thresholds_come_from_the_resolver(self, db, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "PURGE_GRACE_DAYS", 45)
        assert status_thresholds(db) == StatusThresholds(inactive_after_days=30, grace_days=45)
        settings_service.set_value(db, "inactive_after_days", 7, updated_by=None)
        settings_service.set_value(db, "PURGE_GRACE_DAYS", 10, updated_by=None)
        db.commit()
        assert status_thresholds(db) == StatusThresholds(inactive_after_days=7, grace_days=10)


class TestLastActiveOf:
    def test_latest_leg_wins_and_ties_prefer_workout_then_scan(self):
        d = date(2026, 9, 10)
        login = datetime(2026, 9, 12, 8, 0, tzinfo=timezone.utc)
        assert last_active_of(d, d - timedelta(days=1), login) == (login.date(), "login")
        assert last_active_of(d, d, None) == (d, "workout")
        assert last_active_of(None, d, datetime(2026, 9, 10, 23, 0)) == (d, "scan")
        assert last_active_of(None, None, None) == (None, None)
