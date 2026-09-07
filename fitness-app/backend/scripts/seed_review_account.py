"""Seed the App Review demo account (app-store-launch spec §G1).

Run from fitness-app/backend:
    SEED_USER_EMAIL=<reviewer email> SEED_USER_PASSWORD=<password> \\
      venv/bin/python scripts/seed_review_account.py

Creates the account App Review signs in with (or updates it in place) and
lands ten weeks of push/pull/legs training ending yesterday through the
same ``POST /workouts`` implementation the iOS app hits — so e1RM, PRs, XP,
level and rank are computed by the real code paths, never inserted. Weekly
bodyweight goes through the bodyweight upsert. ``scans.unlimited`` is
granted through ``entitlement_service`` exactly as
``grant_owner_unlimited_scans.py`` does — the one sanctioned writer of
``scan_balances.has_unlimited`` (control-plane spec §6.2) — with an audit row.

Idempotent: every session carries a deterministic ``client_id`` the ingest
path recognises, so a second run finds them and reports "already seeded".
Re-running keeps the original dates (it never duplicates history); to seed
fresh dates before a resubmission, purge the account first. Never prints
the email or password.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND_DIR)
load_dotenv(os.path.join(_BACKEND_DIR, ".env"))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

import app.models  # noqa: E402, F401 — register every model
from app.api.bodyweight import log_bodyweight  # noqa: E402
from app.api.workouts import _create_workout_impl  # noqa: E402
from app.core.security import hash_password, verify_password  # noqa: E402
from app.models.bodyweight import BodyweightEntry  # noqa: E402
from app.models.entitlement import EntitlementSource  # noqa: E402
from app.models.exercise import Exercise  # noqa: E402
from app.models.pr import PR  # noqa: E402
from app.models.user import TrainingExperience, User, UserProfile  # noqa: E402
from app.models.workout import WorkoutSession  # noqa: E402
from app.schemas.bodyweight import BodyweightCreate  # noqa: E402
from app.schemas.workout import SetCreate, WorkoutCreate, WorkoutExerciseCreate  # noqa: E402
from app.services import entitlement_service  # noqa: E402
from app.services.audit_service import audit  # noqa: E402
from app.services.xp_service import get_or_create_user_progress  # noqa: E402

REASON = "app-review demo account: scripts/seed_review_account.py"
CLIENT_ID_PREFIX = "review-seed:"
USAGE = (
    "usage: SEED_USER_EMAIL=<reviewer email> SEED_USER_PASSWORD=<password> "
    "venv/bin/python scripts/seed_review_account.py"
)

PROGRAM_WEEKS = 10
# Training days within each week: offsets from the week's first session.
SPLIT_DAYS: Tuple[Tuple[int, str], ...] = ((0, "push"), (2, "pull"), (4, "legs"))
HUNT_NAMES = {"push": "Push Day", "pull": "Pull Day", "legs": "Leg Day"}

# Several analytics surfaces are gated on age / sex / height (spec §G1.2).
PROFILE: Dict[str, Any] = {
    "age": 29,
    "sex": "M",
    "height_inches": 70.0,
    "training_experience": TrainingExperience.INTERMEDIATE,
}

# Top-set weight (lb) per week for the two main lifts of each split. Two
# build blocks around a rep-work week (5) and a deload (6), finishing on
# heavy triples: the e1RM path mints PRs across all ten weeks rather than
# only in week one, and the trend charts have a shape.
MAIN_LIFTS: Dict[str, List[str]] = {
    "push": ["Barbell Bench Press", "Overhead Press"],
    "pull": ["Barbell Deadlift", "Barbell Row"],
    "legs": ["Barbell Back Squat", "Romanian Deadlift"],
}
TOP_SET_LB: Dict[str, List[int]] = {
    "Barbell Bench Press": [170, 175, 180, 185, 165, 150, 185, 190, 195, 205],
    "Overhead Press": [100, 105, 105, 110, 95, 85, 110, 115, 115, 120],
    "Barbell Deadlift": [275, 285, 295, 305, 265, 235, 305, 315, 325, 345],
    "Barbell Row": [155, 160, 165, 170, 150, 135, 170, 175, 180, 185],
    "Barbell Back Squat": [225, 235, 245, 255, 225, 195, 255, 265, 275, 290],
    "Romanian Deadlift": [185, 195, 205, 215, 185, 165, 215, 225, 235, 245],
}
MAIN_REPS = [5, 5, 5, 3, 8, 5, 5, 5, 3, 3]
MAIN_SETS = [4, 4, 4, 3, 3, 3, 4, 4, 3, 3]
MAIN_RPE = [7, 7, 8, 8, 8, 6, 8, 8, 9, 9]
SESSION_RPE = [7, 7, 8, 8, 7, 6, 8, 8, 9, 9]

# (exercise, week-1 weight lb, reps, step added every three weeks)
ACCESSORIES: Dict[str, List[Tuple[str, int, int, int]]] = {
    "push": [
        ("Incline Dumbbell Bench Press", 55, 10, 5),
        ("Lateral Raises", 20, 12, 5),
        ("Tricep Pushdowns", 50, 12, 10),
    ],
    "pull": [
        ("Lat Pulldown", 120, 10, 10),
        ("Face Pulls", 40, 15, 10),
        ("Barbell Curl", 65, 10, 5),
    ],
    "legs": [
        ("Leg Press", 360, 10, 20),
        ("Leg Curl", 90, 12, 10),
        ("Standing Calf Raise", 180, 12, 10),
    ],
}
ACCESSORY_SETS = 3

# Weekly weigh-ins (lb), one per programme week plus one on the anchor day:
# a gentle downward trend with a little noise so the chart isn't flat.
BODYWEIGHT_LB = [178.2, 177.6, 177.9, 177.1, 176.8, 176.2, 176.5, 175.7, 175.3, 174.9, 174.6]


def default_anchor() -> date:
    """The last session lands here: yesterday, never today or the future."""
    return date.today() - timedelta(days=1)


def exercise_names() -> List[str]:
    names: List[str] = []
    for split in ("push", "pull", "legs"):
        names.extend(MAIN_LIFTS[split])
        names.extend(name for name, _, _, _ in ACCESSORIES[split])
    return names


def session_plan(anchor: date) -> List[Dict[str, Any]]:
    """Thirty sessions, three a week, the last one on ``anchor``."""
    last_offset = 7 * (PROGRAM_WEEKS - 1) + SPLIT_DAYS[-1][0]
    start = anchor - timedelta(days=last_offset)
    plan = []
    for week in range(PROGRAM_WEEKS):
        for day, split in SPLIT_DAYS:
            plan.append(
                {
                    "client_id": f"{CLIENT_ID_PREFIX}w{week:02d}:{split}",
                    "local_date": start + timedelta(days=7 * week + day),
                    "week": week,
                    "split": split,
                }
            )
    return plan


def bodyweight_dates(anchor: date) -> List[date]:
    plan = session_plan(anchor)
    firsts = [item["local_date"] for item in plan if item["split"] == SPLIT_DAYS[0][1]]
    return firsts + [anchor]


def _workout_payload(item: Dict[str, Any], exercises: Dict[str, Exercise]) -> WorkoutCreate:
    week, split, local_date = item["week"], item["split"], item["local_date"]
    workout_exercises: List[WorkoutExerciseCreate] = []
    for name in MAIN_LIFTS[split]:
        workout_exercises.append(
            WorkoutExerciseCreate(
                exercise_id=exercises[name].id,
                order_index=len(workout_exercises),
                sets=[
                    SetCreate(
                        weight=TOP_SET_LB[name][week],
                        reps=MAIN_REPS[week],
                        rpe=MAIN_RPE[week],
                        set_number=n,
                    )
                    for n in range(1, MAIN_SETS[week] + 1)
                ],
            )
        )
    for name, base, reps, step in ACCESSORIES[split]:
        workout_exercises.append(
            WorkoutExerciseCreate(
                exercise_id=exercises[name].id,
                order_index=len(workout_exercises),
                sets=[
                    SetCreate(weight=base + step * (week // 3), reps=reps, set_number=n)
                    for n in range(1, ACCESSORY_SETS + 1)
                ],
            )
        )
    day_index = [s for _, s in SPLIT_DAYS].index(split)
    return WorkoutCreate(
        client_id=item["client_id"],
        # Midnight datetime + explicit local_date: the manual-log convention
        # (see core/utils.derive_local_date), so the day is unambiguous.
        date=local_date.isoformat(),
        local_date=local_date,
        name=HUNT_NAMES[split],
        duration_minutes=55 + 5 * ((week + day_index) % 4),
        session_rpe=SESSION_RPE[week],
        exercises=workout_exercises,
    )


def _resolve_exercises(session: Session) -> Dict[str, Exercise]:
    """Library rows for every exercise the programme uses; fail loudly on gaps."""
    found: Dict[str, Exercise] = {}
    missing: List[str] = []
    for name in exercise_names():
        row = (
            session.query(Exercise)
            .filter(Exercise.name == name, Exercise.is_custom == False)
            .order_by(Exercise.created_at)
            .first()
        )
        if row is None:
            missing.append(name)
        else:
            found[name] = row
    if missing:
        raise LookupError(
            "exercise library is missing: " + ", ".join(missing) + " — seed the library first"
        )
    return found


def _ensure_user(session: Session, email: str, password: str) -> Tuple[User, str, str]:
    """Create the account the way ``POST /auth/register`` does, or make the
    existing one match the supplied password. Returns
    ``(user, "created"|"existing", "set"|"unchanged"|"updated")``."""
    user = session.query(User).filter(User.email == email).first()
    if user is None:
        user = User(email=email, password_hash=hash_password(password))
        session.add(user)
        session.flush()
        session.add(UserProfile(user_id=user.id))
        session.commit()
        return user, "created", "set"
    if user.is_deleted:
        raise LookupError(
            "the account for SEED_USER_EMAIL is soft-deleted; purge it before reseeding"
        )
    if verify_password(password, user.password_hash):
        password_state = "unchanged"
    else:
        user.password_hash = hash_password(password)
        # Invalidate outstanding tokens, as a password reset does (spec §4.3).
        user.token_version = (user.token_version or 0) + 1
        password_state = "updated"
    if session.query(UserProfile).filter(UserProfile.user_id == user.id).first() is None:
        session.add(UserProfile(user_id=user.id))
    session.commit()
    return user, "existing", password_state


def _ensure_profile(session: Session, user: User, bodyweight_lb: float) -> List[str]:
    profile = session.query(UserProfile).filter(UserProfile.user_id == user.id).one()
    changed: List[str] = []
    for field, value in {**PROFILE, "bodyweight_lb": bodyweight_lb}.items():
        if getattr(profile, field) != value:
            setattr(profile, field, value)
            changed.append(field)
    if changed:
        session.commit()
    return changed


def _ensure_unlimited(session: Session, user: User) -> Dict[str, Any]:
    """Grant ``scans.unlimited`` through the entitlement service, as
    ``grant_owner_unlimited_scans.py`` does. Commits."""
    key = entitlement_service.KEY_UNLIMITED
    changed = not entitlement_service.is_entitled(session, user.id, key)
    if changed:
        entitlement_service.grant(
            session,
            user_id=user.id,
            key=key,
            value=True,
            source=EntitlementSource.ADMIN_GRANT,
            reason=REASON,
        )
        audit(
            session,
            actor=None,
            action="entitlement.grant",
            target_type="user",
            target_id=user.id,
            after={"key": key, "value": True, "source": EntitlementSource.ADMIN_GRANT.value},
            reason=REASON,
        )
    else:
        # Already granted: just make sure the cached flag agrees.
        entitlement_service.sync_unlimited_flag(session, user.id)
    session.commit()
    balance = entitlement_service.get_or_create_balance(session, user.id)
    return {"entitlement_changed": changed, "has_unlimited": bool(balance.has_unlimited)}


async def _settle_background_tasks() -> None:
    """Let the ingest path's fire-and-forget push notifications finish (they
    no-op without a device token) before the event loop closes."""
    pending = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


async def _seed_history(
    session: Session, user: User, anchor: date, exercises: Dict[str, Exercise]
) -> Dict[str, int]:
    """Sessions in chronological order through the real ingest path, then
    the weekly weigh-ins through the bodyweight upsert."""
    seeded = {
        client_id
        for (client_id,) in session.query(WorkoutSession.client_id)
        .filter(
            WorkoutSession.user_id == user.id,
            WorkoutSession.client_id.like(f"{CLIENT_ID_PREFIX}%"),
        )
        .all()
    }
    created = existing = 0
    for item in session_plan(anchor):
        if item["client_id"] in seeded:
            existing += 1
            continue
        await _create_workout_impl(_workout_payload(item, exercises), user, session)
        created += 1

    dates = bodyweight_dates(anchor)
    weighed = {
        d
        for (d,) in session.query(BodyweightEntry.date)
        .filter(BodyweightEntry.user_id == user.id, BodyweightEntry.date.in_(dates))
        .all()
    }
    bodyweight_created = 0
    for day, weight in zip(dates, BODYWEIGHT_LB):
        if day in weighed:
            continue
        await log_bodyweight(BodyweightCreate(date=day, weight=weight), current_user=user, db=session)
        bodyweight_created += 1

    await _settle_background_tasks()
    return {
        "sessions_created": created,
        "sessions_existing": existing,
        "bodyweight_created": bodyweight_created,
        "bodyweight_existing": len(weighed),
    }


def seed_review_account(
    session: Session, email: str, password: str, *, anchor: Optional[date] = None
) -> Dict[str, Any]:
    """Seed (or re-verify) the demo account. Returns a report; commits.

    Raises ``LookupError`` when the exercise library is incomplete or the
    account is soft-deleted, ``ValueError`` for an anchor that is not in
    the past.
    """
    anchor = anchor or default_anchor()
    if anchor >= date.today():
        raise ValueError("anchor must be in the past — sessions never sit in the future")

    exercises = _resolve_exercises(session)
    user, account, password_state = _ensure_user(session, email, password)
    history = asyncio.run(_seed_history(session, user, anchor, exercises))
    profile_changed = _ensure_profile(session, user, BODYWEIGHT_LB[-1])
    entitlement = _ensure_unlimited(session, user)

    progress = get_or_create_user_progress(session, user.id)
    session.commit()
    plan = session_plan(anchor)
    changed = (
        account == "created"
        or password_state != "unchanged"
        or history["sessions_created"] > 0
        or history["bodyweight_created"] > 0
        or bool(profile_changed)
        or entitlement["entitlement_changed"]
    )
    return {
        "user_id": user.id,
        "account": account,
        "password": password_state,
        "profile_changed": profile_changed,
        **history,
        **entitlement,
        "sessions_total": history["sessions_created"] + history["sessions_existing"],
        "bodyweight_total": history["bodyweight_created"] + history["bodyweight_existing"],
        "first_session": plan[0]["local_date"],
        "last_session": plan[-1]["local_date"],
        "prs": session.query(PR).filter(PR.user_id == user.id).count(),
        "total_xp": progress.total_xp,
        "level": progress.level,
        "rank": progress.rank,
        "changed": changed,
    }


def main() -> int:
    email = (os.environ.get("SEED_USER_EMAIL") or "").strip().lower()
    password = os.environ.get("SEED_USER_PASSWORD") or ""
    if not email or not password:
        print(
            "SEED_USER_EMAIL and SEED_USER_PASSWORD must both be set "
            "(from the environment — never as literals).",
            file=sys.stderr,
        )
        print(USAGE, file=sys.stderr)
        return 2
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL not set", file=sys.stderr)
        return 2

    session = sessionmaker(bind=create_engine(url))()
    try:
        result = seed_review_account(session, email, password)
    except (LookupError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        session.close()

    print(f"user …{result['user_id'][-4:]} account={result['account']} password={result['password']}")
    print(
        f"sessions +{result['sessions_created']} ({result['sessions_total']} total, "
        f"{result['first_session']} → {result['last_session']})"
    )
    print(f"bodyweight +{result['bodyweight_created']} ({result['bodyweight_total']} total)")
    print(
        f"prs={result['prs']} level={result['level']} rank={result['rank']} "
        f"xp={result['total_xp']} has_unlimited={result['has_unlimited']}"
    )
    if result["profile_changed"]:
        print("profile updated: " + ", ".join(result["profile_changed"]))
    if not result["changed"]:
        print("already seeded — no change")
    return 0


if __name__ == "__main__":
    sys.exit(main())
