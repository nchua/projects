"""
Hard purge and the sweep (control-plane spec §8.2, §8.3, §16): the checks,
a user seeded across every table, the metadata guard on ``PURGE_ORDER``,
the dry run / apply of ``purge-eligible``, and the inert startup sweep.
"""
import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import func, or_, select

from app.core import admin_bootstrap
from app.core.config import settings
from app.core.database import Base
from app.models import (
    PR,
    AchievementDefinition,
    BodyweightEntry,
    CoachOutput,
    DailyActivity,
    DailyTrainingLoad,
    DeviceToken,
    Exercise,
    FriendRequest,
    Friendship,
    Goal,
    GoalProgressSnapshot,
    HeartRateSample,
    NotificationPreference,
    PasswordResetToken,
    PRGate,
    PurchaseRecord,
    ScanBalance,
    ScreenshotUsage,
    Set,
    UserAchievement,
    UserDirective,
    UserProgress,
    WhoopConnection,
    WorkoutExercise,
)
from app.models.admin import AdminAuditLog
from app.models.user import User
from app.services import entitlement_service as es
from app.services import purge_service
from app.services.campaign_service import materialize_range
from tests.helpers_admin import grant_admin, soft_delete
from tests.helpers_w1 import MONDAY, add_lift, import_plan

TODAY = date.today()
PURGE_ORDER = purge_service.PURGE_ORDER
ORDER = [step.table for step in PURGE_ORDER]


def _purge(client, headers, user, step_up_body, **extra):
    extra.setdefault("reason", "forced purge for the test")
    body = step_up_body(confirm_email=user.email, **extra)
    return client.post(f"/admin/users/{user.id}/purge", json=body, headers=headers)


def _users_fk_tables():
    """``{table: [columns]}`` for every FK to ``users.id`` in the metadata."""
    out = {}
    for table in Base.metadata.tables.values():
        cols = [c.name for c in table.columns for fk in c.foreign_keys if fk.column.table.name == "users"]
        if cols:
            out[table.name] = cols
    return out


def _rows_referencing(db, user_id: str):
    """Row count per table still pointing at ``user_id`` through any FK to users."""
    counts = {}
    for name, cols in _users_fk_tables().items():
        table = Base.metadata.tables[name]
        where = or_(*(table.c[c] == user_id for c in cols))
        counts[name] = db.execute(select(func.count()).select_from(table).where(where)).scalar()
    return counts


def seed_everything(db, user, friend) -> dict:
    """One row in every table that references the user (plus the cascading children)."""
    tag = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc)

    progress = UserProgress(user_id=user.id)
    db.add(progress)
    db.flush()
    definition = db.query(AchievementDefinition).first()
    if definition is None:
        definition = AchievementDefinition(id=f"ach-{tag}", name="First", description="d", category="milestone", icon="i")
        db.add(definition)
        db.flush()
    db.add(UserAchievement(user_id=user.id, user_progress_id=progress.id, achievement_id=definition.id))

    exercise = Exercise(name=f"Custom Lift {tag}", category="compound", is_custom=True, user_id=user.id)
    db.add(exercise)
    db.flush()
    session = add_lift(db, user.id, TODAY, [(exercise, [(100, 5)])])
    set_row = db.query(Set).join(WorkoutExercise).filter(WorkoutExercise.session_id == session.id).first()
    db.add(HeartRateSample(user_id=user.id, session_id=session.id, set_id=set_row.id, timestamp=now, bpm=140, source="apple_watch"))
    db.add(PR(user_id=user.id, exercise_id=exercise.id, set_id=set_row.id, pr_type="e1rm", achieved_at=now))

    campaign, _ = import_plan(db, user.id, start=MONDAY)
    hunts = materialize_range(db, user.id, MONDAY, MONDAY + timedelta(days=6), today=MONDAY)
    db.add(PRGate(
        user_id=user.id, exercise_id=exercise.id, planned_hunt_id=hunts[0].id, cleared_by_set_id=set_row.id,
        rank="C", name="gate", target_weight=1, target_reps=1, target_e1rm=1, baseline_e1rm=1,
        projected_e1rm=1, weekly_slope=0, condition_at_spawn=50, spawned_at=now, expires_at=now,
    ))
    goal = Goal(user_id=user.id, exercise_id=exercise.id, campaign_id=campaign.id, target_weight=200, deadline=TODAY + timedelta(days=30))
    db.add(goal)
    db.flush()
    db.add(GoalProgressSnapshot(goal_id=goal.id, recorded_at=now, e1rm=100, workout_id=session.id))

    db.add(BodyweightEntry(user_id=user.id, date=now, weight_lb=170))
    db.add(DailyActivity(user_id=user.id, date=TODAY))
    db.add(DailyTrainingLoad(user_id=user.id, local_date=TODAY))
    db.add(CoachOutput(user_id=user.id, kind="debrief", for_date=TODAY, context_hash="h", prompt_version="v1", model="m"))
    db.add(UserDirective(user_id=user.id, date=TODAY, directive_type="rest", message="rest"))
    db.add(ScreenshotUsage(user_id=user.id))
    db.add(ScanBalance(user_id=user.id, scan_credits=3))
    db.flush()
    grant_admin(db, user.id, es.KEY_UNLIMITED, True)
    receipt = PurchaseRecord(user_id=user.id, product_id="com.nickchua.fitnessapp.scan_20",
                             transaction_id=str(int(tag, 16)), credits_added=20, purchase_type="consumable")
    db.add(receipt)
    db.add(PasswordResetToken(user_id=user.id, email=user.email, code="123456", expires_at=now))
    db.add(DeviceToken(user_id=user.id, token=f"tok-{tag}"))
    db.add(NotificationPreference(user_id=user.id, notification_type="level_up"))
    db.add(WhoopConnection(user_id=user.id))
    db.add(FriendRequest(sender_id=user.id, receiver_id=friend.id))
    db.add(FriendRequest(sender_id=friend.id, receiver_id=user.id))
    db.add(Friendship(user_id=user.id, friend_id=friend.id))
    db.add(Friendship(user_id=friend.id, friend_id=user.id))
    db.commit()
    return {"receipt_id": receipt.id, "exercise_id": exercise.id, "session_id": session.id}


@pytest.fixture
def setup(admin_pair):
    headers, actor, target, _ = admin_pair("purge")
    return headers, actor, target


class TestPurgeChecks:
    def test_not_deleted_409(self, client, db, setup, step_up_body):
        headers, _, target = setup
        assert _purge(client, headers, target, step_up_body).status_code == 409
        assert db.query(User).filter(User.id == target.id).count() == 1

    def test_inside_grace_409_unless_forced(self, client, db, setup, step_up_body):
        headers, _, target = setup
        soft_delete(db, target, days_ago=5)
        response = _purge(client, headers, target, step_up_body)
        assert response.status_code == 409 and "grace" in response.json()["detail"]
        assert _purge(client, headers, target, step_up_body, force=True, reason="short").status_code == 422
        assert db.query(User).filter(User.id == target.id).count() == 1
        forced = _purge(client, headers, target, step_up_body, force=True)
        assert forced.status_code == 200, forced.text
        assert db.query(User).filter(User.id == target.id).count() == 0

    def test_past_grace_needs_no_force(self, client, db, setup, step_up_body):
        headers, _, target = setup
        soft_delete(db, target, days_ago=settings.PURGE_GRACE_DAYS + 1)
        response = _purge(client, headers, target, step_up_body, reason="past grace")
        assert response.status_code == 200, response.text
        assert response.json()["tables"]["users"] == 1

    def test_wrong_confirm_email_422(self, client, db, setup, step_up_body):
        headers, _, target = setup
        soft_delete(db, target, days_ago=40)
        body = step_up_body(reason="purge please", confirm_email="someone-else@example.com")
        assert client.post(f"/admin/users/{target.id}/purge", json=body, headers=headers).status_code == 422
        assert db.query(User).filter(User.id == target.id).count() == 1

    def test_admin_and_self_403(self, client, db, setup, admin_user, step_up_body):
        headers, actor, _ = setup
        other, _ = admin_user(email=f"purge-other-admin-{uuid.uuid4().hex[:8]}@example.com")
        soft_delete(db, other, days_ago=40)
        assert _purge(client, headers, other, step_up_body).status_code == 403
        assert _purge(client, headers, actor, step_up_body).status_code == 403
        assert db.query(User).filter(User.id.in_([other.id, actor.id])).count() == 2

    def test_unknown_user_404(self, client, setup, step_up_body):
        headers, _, _ = setup
        body = step_up_body(reason="purge please", confirm_email="x@example.com")
        assert client.post("/admin/users/nope/purge", json=body, headers=headers).status_code == 404


class TestPurgeEndToEnd:
    def test_seeded_user_is_gone_receipt_unlinked_audit_kept(
        self, client, db, setup, create_test_user, step_up_body
    ):
        headers, actor, target = setup
        friend, _ = create_test_user(email=f"purge-friend-{uuid.uuid4().hex[:8]}@example.com")
        seeded = seed_everything(db, target, friend)
        before = purge_service.count_rows(db, target.id)
        assert all(n >= 1 for n in before.values()), before  # the seed covers every step
        soft_delete(db, target, days_ago=40)

        response = client.post(
            f"/admin/users/{target.id}/purge", headers={**headers, "X-Request-ID": "req-purge"},
            json=step_up_body(reason="past grace", confirm_email=target.email),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["user_id"] == target.id and body["tables"]["users"] == 1
        assert body["tables"]["purchase_records"] == 1 and body["tables"]["friendships"] == 2

        db.expire_all()
        assert _rows_referencing(db, target.id) == {name: 0 for name in _users_fk_tables()}
        assert db.query(User).filter(User.id == target.id).count() == 0
        assert db.query(Exercise).filter(Exercise.id == seeded["exercise_id"]).count() == 0
        assert db.query(Set).join(WorkoutExercise).filter(WorkoutExercise.session_id == seeded["session_id"]).count() == 0
        receipt = db.query(PurchaseRecord).filter(PurchaseRecord.id == seeded["receipt_id"]).one()
        assert receipt.user_id is None and receipt.credits_added == 20

        row = db.query(AdminAuditLog).filter(AdminAuditLog.id == body["audit_id"]).one()
        assert row.action == "user.purge" and row.target_id == target.id and row.actor_user_id == actor.id
        assert row.request_id == "req-purge" and row.before == before == body["tables"]
        assert row.after == {"force": False}

        # The friend's account and their side of the relationship rows survive.
        assert db.query(User).filter(User.id == friend.id).one().is_deleted is False
        assert client.get(f"/admin/users/{target.id}", headers=headers).status_code == 404
        assert client.get(f"/admin/users/{friend.id}", headers=headers).status_code == 200


class TestPurgeOrderMetadata:
    def test_every_fk_to_users_is_in_purge_order(self):
        referencing = set(_users_fk_tables())
        missing = referencing - set(ORDER)
        assert not missing, f"tables with an FK to users.id missing from PURGE_ORDER: {sorted(missing)}"
        assert "admin_audit_log" not in ORDER  # no FK: the trail outlives the account
        assert ORDER[-1] == "users"
        assert len(ORDER) == len(set(ORDER))

    def test_unlink_and_multi_column_steps(self):
        by_table = {step.table: step for step in PURGE_ORDER}
        assert by_table["purchase_records"].unlink is True
        assert set(by_table["friend_requests"].columns) == {"sender_id", "receiver_id"}
        assert set(by_table["friendships"].columns) == {"user_id", "friend_id"}
        assert by_table["goal_progress_snapshots"].via == "goals"

    def test_children_come_before_parents_for_non_cascading_fks(self):
        """Every FK without ON DELETE between two ordered tables points forward in the order."""
        position = {name: i for i, name in enumerate(ORDER)}
        violations = []
        for table in Base.metadata.tables.values():
            if table.name not in position:
                continue
            for column in table.columns:
                for fk in column.foreign_keys:
                    parent = fk.column.table.name
                    if parent in position and fk.ondelete is None and position[table.name] > position[parent]:
                        violations.append(f"{table.name}.{column.name} -> {parent}")
        assert not violations, violations
        # Children whose parent cascades at the DB level are still deleted before the grandparent rows they pin.
        assert position["prs"] < position["workout_sessions"]           # prs.set_id -> sets
        assert position["pr_gates"] < position["workout_sessions"]      # pr_gates.cleared_by_set_id -> sets
        assert position["goal_progress_snapshots"] < position["workout_sessions"]


class TestPurgeEligible:
    URL = "/admin/maintenance/purge-eligible"

    @pytest.fixture
    def cohort(self, db, create_test_user, admin_user):
        tag = uuid.uuid4().hex[:8]
        old, _ = create_test_user(email=f"eligible-old-{tag}@example.com")
        soft_delete(db, old, days_ago=40)
        fresh, _ = create_test_user(email=f"eligible-fresh-{tag}@example.com")
        soft_delete(db, fresh, days_ago=5)
        alive, _ = create_test_user(email=f"eligible-alive-{tag}@example.com")
        gone_admin, _ = admin_user(email=f"eligible-admin-{tag}@example.com")
        soft_delete(db, gone_admin, days_ago=40)
        return old, fresh, alive, gone_admin

    def test_dry_run_lists_only_past_grace_and_writes_nothing(self, client, db, setup, cohort):
        headers, _, _ = setup
        old, fresh, alive, gone_admin = cohort
        audits = db.query(AdminAuditLog).count()
        response = client.post(self.URL, json={"reason": "weekly look"}, headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["dry_run"] is True and body["purged"] == []
        assert [row["user_id"] for row in body["eligible"]] == [old.id]
        assert body["eligible"][0]["days_deleted"] == 40
        assert db.query(User).filter(User.id.in_([old.id, fresh.id, alive.id, gone_admin.id])).count() == 4
        assert db.query(AdminAuditLog).count() == audits

    def test_apply_purges_eligible_and_audits_each_plus_a_summary(self, client, db, setup, cohort, step_up_body):
        headers, actor, _ = setup
        old, fresh, alive, gone_admin = cohort
        assert client.post(self.URL, json={"reason": "sweep", "dry_run": False}, headers=headers).status_code == 401
        response = client.post(self.URL, json=step_up_body(reason="sweep", dry_run=False),
                               headers={**headers, "X-Request-ID": "req-sweep"})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["dry_run"] is False and [p["user_id"] for p in body["purged"]] == [old.id]
        assert db.query(User).filter(User.id == old.id).count() == 0
        assert db.query(User).filter(User.id.in_([fresh.id, alive.id, gone_admin.id])).count() == 3
        rows = db.query(AdminAuditLog).filter(AdminAuditLog.request_id == "req-sweep").all()
        assert sorted(r.action for r in rows) == ["maintenance.purge_sweep", "user.purge"]
        summary = next(r for r in rows if r.action == "maintenance.purge_sweep")
        assert summary.actor_user_id == actor.id
        assert summary.after == {"eligible": 1, "purged": [old.id], "blocked": []}


class TestStartupSweep:
    def test_disabled_flag_is_inert(self, db, monkeypatch):
        monkeypatch.setattr(settings, "PURGE_SWEEP_ENABLED", False)
        audits = db.query(AdminAuditLog).count()
        assert purge_service.run_startup_sweep() == "disabled"
        assert purge_service.schedule_startup_sweep(delay=0) is None
        assert db.query(AdminAuditLog).count() == audits

    def test_skipped_on_sqlite(self, db, monkeypatch, create_test_user):
        monkeypatch.setattr(settings, "PURGE_SWEEP_ENABLED", True)
        old, _ = create_test_user(email=f"sweep-old-{uuid.uuid4().hex[:8]}@example.com")
        soft_delete(db, old, days_ago=40)
        assert purge_service.run_startup_sweep() == "sqlite"
        assert db.query(User).filter(User.id == old.id).count() == 1
        assert db.query(AdminAuditLog).filter(AdminAuditLog.action == "maintenance.purge_sweep").count() == 0

    async def test_schedules_a_task_on_the_running_loop(self, monkeypatch):
        monkeypatch.setattr(settings, "PURGE_SWEEP_ENABLED", True)
        task = purge_service.schedule_startup_sweep(delay=0)
        assert isinstance(task, asyncio.Task)
        assert await task == "sqlite"

    def test_run_startup_tasks_never_raises_with_the_flag_on(self, monkeypatch):
        monkeypatch.setattr(settings, "PURGE_SWEEP_ENABLED", True)
        assert admin_bootstrap.run_startup_tasks() is None  # no loop: logged, not raised
