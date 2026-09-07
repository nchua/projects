"""
The App Review demo-account seed (app-store-launch spec §G1) must be
credential-free, idempotent, and derive e1RM / PRs / XP / rank through the
real ingest path rather than inserting them.
"""
import re
from datetime import date, timedelta

import pytest

from app.api import workouts as workouts_api
from app.core.e1rm import e1rm_for_set, get_user_e1rm_formula
from app.core.security import verify_password
from app.models.admin import AdminAuditLog
from app.models.bodyweight import BodyweightEntry
from app.models.entitlement import UserEntitlement
from app.models.pr import PR, PRType
from app.models.progress import UserProgress
from app.models.scan_balance import ScanBalance
from app.models.user import User, UserProfile
from app.models.workout import Set, WorkoutExercise, WorkoutSession
from app.services import entitlement_service as es
from app.services.xp_service import get_rank_for_level, xp_for_level
from tests.helpers_admin import load_script
from tests.helpers_migrations import BACKEND

EMAIL = "review-seed@example.com"
PASSWORD = "ReviewPass123!"
SCRIPT = BACKEND / "scripts" / "seed_review_account.py"


def _snapshot(db, user_id: str) -> dict:
    db.expire_all()
    progress = db.query(UserProgress).filter(UserProgress.user_id == user_id).one()
    return {
        "sessions": db.query(WorkoutSession).filter(WorkoutSession.user_id == user_id).count(),
        "sets": (
            db.query(Set)
            .join(WorkoutExercise)
            .join(WorkoutSession)
            .filter(WorkoutSession.user_id == user_id)
            .count()
        ),
        "prs": db.query(PR).filter(PR.user_id == user_id).count(),
        "bodyweight": db.query(BodyweightEntry).filter(BodyweightEntry.user_id == user_id).count(),
        "entitlements": db.query(UserEntitlement).filter(UserEntitlement.user_id == user_id).count(),
        "audit": db.query(AdminAuditLog).filter(AdminAuditLog.target_id == user_id).count(),
        "xp": progress.total_xp,
        "level": progress.level,
        "workouts": progress.total_workouts,
        "password_hash": db.query(User).filter(User.id == user_id).one().password_hash,
    }


class TestSeedReviewAccount:
    def test_seeds_through_the_real_paths_and_derives_state(self, db, seeded_exercises):
        module = load_script("seed_review_account")
        # Shared symbols, no drift: the script lands data the way the app does.
        assert module._create_workout_impl is workouts_api._create_workout_impl
        assert module.entitlement_service.grant is es.grant
        assert module.default_anchor() == date.today() - timedelta(days=1)

        report = module.seed_review_account(db, EMAIL, PASSWORD)
        assert report["account"] == "created" and report["changed"] is True
        assert report["sessions_created"] == 30 and report["sessions_existing"] == 0

        user = db.query(User).filter(User.email == EMAIL).one()
        assert verify_password(PASSWORD, user.password_hash)

        # Ten weeks, three a week, ending yesterday, nothing in the future.
        sessions = (
            db.query(WorkoutSession)
            .filter(WorkoutSession.user_id == user.id)
            .order_by(WorkoutSession.local_date)
            .all()
        )
        yesterday = date.today() - timedelta(days=1)
        assert len(sessions) == 30
        assert all(s.deleted_at is None and s.client_id.startswith("review-seed:") for s in sessions)
        assert sessions[-1].local_date == yesterday
        assert sessions[0].local_date == yesterday - timedelta(days=67)
        assert all(4 <= len(s.workout_exercises) <= 6 for s in sessions)

        # e1RM on every set is what the e1RM service computes for that set.
        formula = get_user_e1rm_formula(db, user.id)
        sets = [st for s in sessions for we in s.workout_exercises for st in we.sets]
        assert sets and all(
            st.e1rm == e1rm_for_set(st.weight_lb, st.reps, st.rpe, st.rir, formula) for st in sets
        )

        # PRs fell out of those sets: each one points at a seeded set and
        # carries that set's numbers, and they are spread across the weeks.
        set_by_id = {st.id: st for st in sets}
        prs = db.query(PR).filter(PR.user_id == user.id).all()
        assert len(prs) >= 10
        for pr in prs:
            assert pr.set_id in set_by_id, "PR not linked to a seeded set"
            st = set_by_id[pr.set_id]
            if pr.pr_type == PRType.E1RM:
                assert pr.value == st.e1rm
            else:
                assert (pr.weight, pr.reps) == (st.weight, st.reps)
        assert len({pr.achieved_at.date() for pr in prs}) >= 6
        assert max(pr.achieved_at.date() for pr in prs) > yesterday - timedelta(weeks=4)

        # Rank and level are whatever the XP service says the XP is worth.
        progress = db.query(UserProgress).filter(UserProgress.user_id == user.id).one()
        assert progress.total_workouts == 30
        assert progress.total_prs == len(prs)
        assert progress.level > 1
        assert xp_for_level(progress.level) <= progress.total_xp < xp_for_level(progress.level + 1)
        assert progress.rank == get_rank_for_level(progress.level)
        assert progress.last_workout_date == yesterday
        assert report["level"] == progress.level and report["rank"] == progress.rank

        # Weekly bodyweight with a trend; profile populated for the gated surfaces.
        weights = (
            db.query(BodyweightEntry)
            .filter(BodyweightEntry.user_id == user.id)
            .order_by(BodyweightEntry.date)
            .all()
        )
        assert len(weights) == 11 and weights[-1].date == yesterday
        assert weights[0].weight_lb > weights[-1].weight_lb
        profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).one()
        assert profile.age and profile.sex and profile.height_inches
        assert profile.bodyweight_lb == weights[-1].weight_lb

        # Unlimited scans via the entitlement path, audited, flag synced.
        rows = db.query(UserEntitlement).filter(UserEntitlement.user_id == user.id).all()
        assert [(r.key, r.source) for r in rows] == [(es.KEY_UNLIMITED, "admin_grant")]
        assert db.query(ScanBalance).filter(ScanBalance.user_id == user.id).one().has_unlimited
        audit_row = (
            db.query(AdminAuditLog)
            .filter(AdminAuditLog.action == "entitlement.grant", AdminAuditLog.target_id == user.id)
            .one()
        )
        assert audit_row.actor_user_id is None and audit_row.reason == module.REASON

    def test_second_run_changes_nothing(self, db, seeded_exercises):
        module = load_script("seed_review_account")
        first = module.seed_review_account(db, EMAIL, PASSWORD)
        before = _snapshot(db, first["user_id"])

        second = module.seed_review_account(db, EMAIL, PASSWORD)
        assert second["user_id"] == first["user_id"]
        assert second["changed"] is False
        assert second["account"] == "existing" and second["password"] == "unchanged"
        assert second["sessions_created"] == 0 and second["sessions_existing"] == 30
        assert second["bodyweight_created"] == 0 and second["entitlement_changed"] is False
        assert _snapshot(db, first["user_id"]) == before

    def test_existing_account_gets_the_supplied_password(self, db, seeded_exercises, create_test_user):
        module = load_script("seed_review_account")
        user, _ = create_test_user(email=EMAIL, password="OldPass123!")
        report = module.seed_review_account(db, EMAIL, PASSWORD)
        assert report["user_id"] == user.id
        assert report["account"] == "existing" and report["password"] == "updated"
        db.expire_all()
        assert verify_password(PASSWORD, db.query(User).filter(User.id == user.id).one().password_hash)

    def test_refuses_a_deleted_account_and_a_future_anchor(self, db, seeded_exercises, deleted_user):
        module = load_script("seed_review_account")
        with pytest.raises(LookupError):
            module.seed_review_account(db, deleted_user.email, PASSWORD)
        with pytest.raises(ValueError):
            module.seed_review_account(db, EMAIL, PASSWORD, anchor=date.today())

    def test_refuses_to_run_without_credentials(self, monkeypatch, capsys):
        # Load first: the module's load_dotenv would otherwise refill the vars.
        module = load_script("seed_review_account")
        for name in ("SEED_USER_EMAIL", "SEED_USER_PASSWORD"):
            monkeypatch.delenv(name, raising=False)
        assert module.main() != 0
        assert "SEED_USER_EMAIL" in capsys.readouterr().err

        monkeypatch.setenv("SEED_USER_EMAIL", EMAIL)  # email alone is not enough
        assert module.main() != 0
        assert "SEED_USER_PASSWORD" in capsys.readouterr().err

    def test_source_has_no_literal_credentials(self):
        source = SCRIPT.read_text()
        assert "SEED_USER_EMAIL" in source and "SEED_USER_PASSWORD" in source
        assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", source), "literal address in seed script"
