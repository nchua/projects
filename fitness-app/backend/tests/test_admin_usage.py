"""
Usage aggregates on SQLite, bucketed by the user's local day (spec §9.3 /
§16 ``test_admin_usage``): per-user + fleet + the unlimited drift list.
"""
import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.core.database import mark_read_only
from app.models.activity import DailyActivity
from app.models.scan_balance import PurchaseRecord, ScanBalance
from app.models.screenshot_usage import ScreenshotUsage
from app.models.user import User
from app.services import admin_read_service as rs
from app.services import admin_usage_service as us
from app.services import entitlement_service as es
from app.services import settings_service
from app.services.campaign_service import monday_of
from tests.helpers_admin import grant_admin
from tests.helpers_w1 import add_lift, add_run, family_exercise, make_user

# Fixed, recent-enough anchors: a Friday and the following Saturday 03:30Z.
TODAY = date.today()
MONDAY = monday_of(TODAY) - timedelta(weeks=1)      # last week's Monday
FRIDAY = MONDAY + timedelta(days=4)
SATURDAY_0330Z = datetime.combine(FRIDAY + timedelta(days=1), time(3, 30))


class TestUserUsage:
    def test_buckets_by_local_day_and_ports_every_section(self, db, create_test_user):
        user = make_user(create_test_user, "usage")
        bench = family_exercise(db, "Barbell Bench Press")
        # Stamped Friday, stored as a Saturday-UTC instant → Friday's ISO week.
        add_lift(db, user.id, FRIDAY, [(bench, [(135, 5, 8), (145, 3, None)])],
                 instant=SATURDAY_0330Z, name="Push", duration_minutes=50)
        # Legacy midnight row (no local_date) → that calendar day.
        add_lift(db, user.id, MONDAY, [(bench, [(155, 2, 9)])],
                 instant=datetime.combine(MONDAY, time.min), stamp_local=False, name="Push")
        # Legacy non-midnight instant → its UTC day; a run (cardio + miles).
        add_run(db, user.id, MONDAY + timedelta(days=2), 5.0,
                instant=datetime.combine(MONDAY + timedelta(days=2), time(14, 0)), stamp_local=False,
                duration_seconds=2700, hk_uuid=str(uuid.uuid4()), avg_heart_rate=150,
                mile_splits=[540, 540, 540, 540, 540])
        # Soft-deleted → ignored everywhere.
        gone = add_lift(db, user.id, FRIDAY, [(bench, [(225, 1, None)])], name="Push")
        gone.deleted_at = datetime.now(timezone.utc)
        db.add(ScreenshotUsage(user_id=user.id, screenshots_count=2))
        db.add(ScreenshotUsage(user_id=user.id, screenshots_count=1))
        db.add(DailyActivity(user_id=user.id, date=TODAY - timedelta(days=1), source="whoop",
                             recovery_score=70, hrv=60, sleep_hours=7.5))
        db.add(DailyActivity(user_id=user.id, date=TODAY - timedelta(days=1), source="apple_fitness",
                             steps=9000))
        db.commit()

        usage = us.user_usage(db, user.id, weeks=8, today=TODAY)

        label = us.iso_week_label(FRIDAY)
        assert [w.week for w in usage.sessions_by_week] == [label]
        week = usage.sessions_by_week[0]
        assert (week.strength, week.cardio, week.other) == (2, 1, 0)
        assert week.miles == 5.0
        assert usage.kinds == {"strength": 2, "cardio": 1}
        assert {(s.origin, s.hr_source): s.sessions for s in usage.sources} == {
            ("app", "none"): 2, ("hk", "apple_watch"): 1,
        }

        top = usage.top_exercises
        assert [t.name for t in top] == ["Barbell Bench Press"]
        assert (top[0].sessions, top[0].sets, top[0].sets_with_rpe) == (2, 3, 2)
        assert top[0].best_e1rm == round(155 * (1 + 2 / 30), 1)

        bench_series = next(b for b in usage.big_three if b.lift == "bench")
        assert bench_series.weeks_with_data == 1
        assert bench_series.series[0].week_start == MONDAY
        assert bench_series.series[0].sets == 3
        assert all(b.series == [] for b in usage.big_three if b.lift != "bench")

        meta = usage.session_meta
        assert (meta.sessions, meta.named, meta.with_session_rpe, meta.with_splits) == (3, 2, 0, 1)
        assert meta.with_avg_hr == 1

        assert usage.runs[0].miles == 5.0
        assert usage.runs[0].duration_minutes == 45
        assert usage.runs[0].pace_min_per_mile == 9.0
        assert usage.runs[0].local_date == MONDAY + timedelta(days=2)
        assert usage.runs[0].has_splits is True

        assert (usage.scans.scans, usage.scans.screenshots) == (2, 3)
        assert usage.scans.by_week[0].week == us.iso_week_label(TODAY)

        cover = {c.source: c for c in usage.activity_coverage}
        assert cover["whoop"].recovery == 1 and cover["whoop"].steps == 0
        assert cover["apple_fitness"].steps == 1
        assert usage.latest_daily_activity_date == TODAY - timedelta(days=1)
        assert usage.integrations.whoop_connected is False
        assert usage.integrations.scan_credits is None
        assert usage.gates_by_status == {}

    def test_empty_user(self, db, create_test_user):
        user = make_user(create_test_user, "empty")
        usage = us.user_usage(db, user.id, weeks=4, today=TODAY)
        assert usage.sessions_by_week == [] and usage.kinds == {}
        assert usage.session_meta.sessions == 0 and usage.session_meta.avg_duration_minutes is None
        assert usage.runs == [] and usage.scans.scans == 0

    def test_http_route(self, client, admin_headers, create_test_user):
        headers, _ = admin_headers(email="owner-usage@example.com")
        user = make_user(create_test_user, "http")
        response = client.get(f"/admin/users/{user.id}/usage", headers=headers, params={"weeks": 4})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["weeks"] == 4 and body["user_id"] == user.id
        assert response.headers["cache-control"] == "no-store"
        assert client.get(f"/admin/users/{user.id}/usage", headers=headers,
                          params={"weeks": 0}).status_code == 422
        assert client.get("/admin/users/nope/usage", headers=headers).status_code == 404


class TestFleetUsage:
    def test_counts_weeks_balances_and_drift(self, db, create_test_user, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "PURGE_GRACE_DAYS", 30)
        before = us.fleet_usage(db, weeks=4, counts=rs.fleet_counts(db), today=TODAY)

        a = make_user(create_test_user, "fleet-a")
        b = make_user(create_test_user, "fleet-b")
        old = make_user(create_test_user, "fleet-old")
        old.is_deleted = True
        old.deleted_at = datetime.now(timezone.utc) - timedelta(days=45)
        recent = make_user(create_test_user, "fleet-recent")
        recent.is_deleted = True
        recent.deleted_at = datetime.now(timezone.utc) - timedelta(days=2)
        db.commit()
        bench = family_exercise(db, "Barbell Bench Press")
        add_lift(db, a.id, FRIDAY, [(bench, [(100, 5)])], instant=SATURDAY_0330Z)
        add_lift(db, b.id, FRIDAY, [(bench, [(100, 5)])],
                 instant=datetime.combine(FRIDAY, time.min), stamp_local=False)
        add_lift(db, a.id, TODAY, [(bench, [(100, 5)])])
        # Drift: a cached flag with no entitlement behind it.
        db.add(ScanBalance(user_id=b.id, scan_credits=5, has_unlimited=True))
        db.add(ScanBalance(user_id=a.id, scan_credits=10, has_unlimited=False))
        db.commit()
        grant_admin(db, a.id, es.KEY_UNLIMITED, True)  # synced → no drift
        db.commit()

        after = us.fleet_usage(db, weeks=4, counts=rs.fleet_counts(db), today=TODAY)
        assert after.users.total == before.users.total + 4
        assert after.users.deleted == before.users.deleted + 2
        assert after.users.purge_eligible == before.users.purge_eligible + 1
        assert after.users.active_7d >= before.users.active_7d + 1
        assert after.users.active_30d >= before.users.active_30d + 2

        weeks = {w.week: w for w in after.sessions_by_week}
        last_week = weeks[us.iso_week_label(FRIDAY)]
        assert last_week.sessions >= 2 and last_week.active_users >= 2

        assert after.balances.rows == before.balances.rows + 2
        assert after.balances.unlimited_count == before.balances.unlimited_count + 2
        assert after.balances.credits_total == before.balances.credits_total + 15

        drift = {row.user_id: row for row in after.unlimited_flag_drift}
        assert b.id in drift and drift[b.id].has_unlimited is True and drift[b.id].derived is False
        assert a.id not in drift

        assert after.exercises.total >= before.exercises.total + 1
        assert after.generated_at.tzinfo is not None

    def test_plan_rollups_agree_with_plans_for(self, db, create_test_user):
        """The Overview tiles' splits (v2.3): Unlimited by source, purchased credits outstanding, scans by plan."""
        before = us.fleet_usage(db, weeks=4, counts=rs.fleet_counts(db), today=TODAY)
        free_default = int(settings_service.get(db, "FREE_MONTHLY_SCANS"))
        granted = make_user(create_test_user, "roll-granted")
        bought = make_user(create_test_user, "roll-bought")
        credits = make_user(create_test_user, "roll-credits")
        free = make_user(create_test_user, "roll-free")
        gone = make_user(create_test_user, "roll-gone")
        gone.is_deleted = True
        gone.deleted_at = datetime.now(timezone.utc)
        db.add(ScanBalance(user_id=credits.id, scan_credits=free_default + 30, has_unlimited=False))
        db.add(ScanBalance(user_id=bought.id, scan_credits=free_default + 5, has_unlimited=True))  # credits wait underneath
        db.add(ScanBalance(user_id=gone.id, scan_credits=free_default + 99, has_unlimited=False))  # deleted: not outstanding
        db.commit()
        grant_admin(db, granted.id, es.KEY_UNLIMITED, True)
        product = es.get_product(db, es.UNLIMITED_PRODUCT_ID)
        record = PurchaseRecord(user_id=bought.id, product_id=product.id, credits_added=0, purchase_type="non_consumable",
                                transaction_id=str(9_000_000_000 + int(uuid.uuid4().hex[:6], 16)), verified=True, environment="Sandbox")
        db.add(record)
        db.flush()
        # the receipt decides the source (§3.1), not the row's own `source` — the SQL twin's CASE must agree
        es.grant(db, user_id=bought.id, key=es.KEY_UNLIMITED, value=True, source="admin_grant", purchase_record_id=record.id)
        # an override-aware purchased count: 15 credits above a free_monthly override of 10 = 5 purchased (not 15 - default)
        overridden = make_user(create_test_user, "roll-override")
        db.add(ScanBalance(user_id=overridden.id, scan_credits=15, has_unlimited=False))
        grant_admin(db, overridden.id, es.KEY_FREE_MONTHLY, 10)
        # the newest active row wins: an explicit false over an older true is not Unlimited
        revoked = make_user(create_test_user, "roll-revoked")
        grant_admin(db, revoked.id, es.KEY_UNLIMITED, True)
        db.commit()
        grant_admin(db, revoked.id, es.KEY_UNLIMITED, False)
        db.commit()
        now = datetime.now(timezone.utc)
        for user, n in ((free, 2), (credits, 1), (bought, 3), (granted, 1), (gone, 4)):
            for _ in range(n):
                db.add(ScreenshotUsage(user_id=user.id, screenshots_count=1, created_at=now - timedelta(days=3)))
        db.add(ScreenshotUsage(user_id=free.id, screenshots_count=1, created_at=now - timedelta(days=40)))  # outside 28 d
        db.commit()

        after = us.fleet_usage(db, weeks=4, counts=rs.fleet_counts(db), today=TODAY)
        assert after.by_plan_source.admin_grant == before.by_plan_source.admin_grant + 1
        assert after.by_plan_source.purchase == before.by_plan_source.purchase + 1
        assert after.by_plan_source.backfill == before.by_plan_source.backfill
        assert after.purchased_credits_total == before.purchased_credits_total + 30 + 5 + 5
        assert after.scans_4wk_by_plan.free == before.scans_4wk_by_plan.free + 2  # the 40-day-old scan is outside the window
        assert after.scans_4wk_by_plan.credits == before.scans_4wk_by_plan.credits + 1 + 4  # a deleted hunter's scans still count under its plan
        assert after.scans_4wk_by_plan.unlimited == before.scans_4wk_by_plan.unlimited + 4
        assert after.scans_4wk_by_plan.override == before.scans_4wk_by_plan.override
        # the tile counts (v2.4) are the same grouped query: live hunters only, by the §3.1 / §3.3 twins
        assert after.users.by_plan.unlimited == before.users.by_plan.unlimited + 2  # granted + bought; `revoked` is not
        assert after.users.by_plan.override == before.users.by_plan.override + 1
        assert after.users.by_plan.credits == before.users.by_plan.credits + 1
        assert after.users.by_plan.free == before.users.by_plan.free + 2  # free + revoked
        live = lambda u: u.by_status.active + u.by_status.inactive  # noqa: E731
        assert live(after.users) == live(before.users) + 6  # gone is deleted
        assert after.users.by_status.deleted == before.users.by_status.deleted + 1
        assert after.users.by_status.purge_eligible == before.users.by_status.purge_eligible
        assert after.users.new_7d == before.users.new_7d + 6

    def test_drift_uses_newest_active_row_like_the_writer(self, db, create_test_user):
        user = make_user(create_test_user, "drift-newest")
        grant_admin(db, user.id, es.KEY_UNLIMITED, True)
        db.commit()
        grant_admin(db, user.id, es.KEY_UNLIMITED, False)  # newer explicit False wins
        db.commit()
        balance = db.query(ScanBalance).filter_by(user_id=user.id).one()
        assert balance.has_unlimited is False  # what sync_unlimited_flag derived
        assert user.id not in {row.user_id for row in us.unlimited_flag_drift(db)}

    def test_http_route(self, client, admin_headers):
        headers, _ = admin_headers(email="owner-fleet@example.com")
        response = client.get("/admin/usage", headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body) == {
            "generated_at", "weeks", "users", "sessions_by_week", "scans_by_week", "balances",
            "integrations", "exercises", "unlimited_flag_drift",
            "by_plan_source", "purchased_credits_total", "scans_4wk_by_plan",  # console v2 §7.4 v2.3
        }
        assert set(body["by_plan_source"]) == {"purchase", "admin_grant", "backfill"}
        assert set(body["users"]) == {"total", "deleted", "admins", "active_7d", "active_30d", "purge_eligible", "by_status", "by_plan", "new_7d"}
        assert set(body["users"]["by_status"]) == {"active", "inactive", "deleted", "purge_eligible"}
        assert set(body["users"]["by_plan"]) == {"unlimited", "override", "credits", "free"}
        assert set(body["scans_4wk_by_plan"]) == {"free", "credits", "unlimited", "override"}
        assert body["weeks"] == 20
        assert client.get("/admin/usage", headers=headers, params={"weeks": 500}).status_code == 422


class TestHelpers:
    @pytest.mark.parametrize(
        "day,label", [(date(2026, 1, 1), "2026-W01"), (date(2026, 9, 6), "2026-W36"),
                      (date(2027, 1, 3), "2026-W53")],
    )
    def test_iso_week_label(self, day, label):
        assert us.iso_week_label(day) == label

    def test_mark_read_only_is_noop_on_sqlite(self, db):
        mark_read_only(db)
        assert db.query(User).count() >= 0
