"""Read-only prod diagnostic: why has no PR Gate spawned, and how well are
Condition's inputs fed?

Replicates evaluate_gate_spawns() rule-by-rule WITHOUT writing (no
expire_stale_gates, no db.add/commit). Also reports WHOOP connection state
and daily_activity input coverage for the last 14 days.

Run from fitness-app/backend with the venv python so app imports resolve.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.getcwd())

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from sqlalchemy import create_engine, func, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

db_url = os.environ.get("DATABASE_URL", "")
if not db_url:
    sys.exit("DATABASE_URL not set — aborting.")

engine = create_engine(db_url)
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

from app.models.activity import DailyActivity  # noqa: E402
from app.models.gate import PRGate  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.workout import WorkoutSession  # noqa: E402
from app.services.condition_service import compute_condition  # noqa: E402
from app.services.gate_service import (  # noqa: E402
    CONDITION_BATTLE_READY_MIN,
    GATE_WINDOW_DAYS,
    MAX_OPEN_GATES_TOTAL,
    SPAWN_MIN_FACTOR,
    TARGET_MAX_FACTOR,
    _candidate_lifts,
    _preferred_reps,
    _select_target_set,
)
from app.services.trend_service import (  # noqa: E402
    projected_e1rm as project_e1rm,
)
from app.services.trend_service import (  # noqa: E402
    weekly_best_e1rm_series,
    weekly_slope,
)

# ── pick the primary user (most workout sessions) ──
row = (
    db.query(WorkoutSession.user_id, func.count(WorkoutSession.id).label("n"))
    .filter(WorkoutSession.deleted_at.is_(None))
    .group_by(WorkoutSession.user_id)
    .order_by(text("n DESC"))
    .first()
)
if row is None:
    sys.exit("No workouts in DB.")
user_id = row.user_id
user = db.query(User).filter(User.id == user_id).first()
print(f"USER: id={user_id} workouts={row.n}")

# ── WHOOP connection state ──
try:
    from app.models.whoop import WhoopConnection

    conns = db.query(WhoopConnection).all()
    if conns:
        for c in conns:
            print(f"WHOOP: connected user={c.user_id} scope={c.scope!r}")
    else:
        print("WHOOP: no connection rows (OAuth never completed)")
except Exception as exc:  # model name may differ
    print(f"WHOOP: model import failed ({exc}) — trying raw SQL")
    try:
        n = db.execute(text("SELECT count(*) FROM whoop_connections")).scalar()
        scopes = db.execute(
            text("SELECT scope FROM whoop_connections LIMIT 5")
        ).fetchall()
        print(f"WHOOP: {n} connection rows, scopes={scopes}")
    except Exception as exc2:
        print(f"WHOOP: raw SQL also failed: {exc2}")

# ── daily_activity input coverage, last 14 days ──
today = datetime.now(timezone.utc).date()
since = today - timedelta(days=13)
acts = (
    db.query(DailyActivity)
    .filter(DailyActivity.user_id == user_id, DailyActivity.date >= since)
    .order_by(DailyActivity.date)
    .all()
)
print(f"\nDAILY_ACTIVITY last 14 days ({since}..{today}): {len(acts)} rows")
fields = ["strain", "recovery_score", "hrv", "resting_heart_rate", "sleep_hours"]
counts = {f: 0 for f in fields}
for a in acts:
    present = [f for f in fields if getattr(a, f) is not None]
    for f in present:
        counts[f] += 1
    print(f"  {a.date} src={a.source:<16} " + " ".join(
        f"{f}={'Y' if getattr(a, f) is not None else '-'}" for f in fields
    ))
print("COVERAGE: " + ", ".join(f"{f}: {counts[f]}/14" for f in fields))

# ── condition right now (server UTC day, as GET /gates sees it) ──
cond = compute_condition(db, user_id)
print(f"\nCONDITION (UTC day {today}): score={cond['score']} band={cond.get('band')}")
print(f"  spawn gate requires >= {CONDITION_BATTLE_READY_MIN}: "
      f"{'PASS' if cond['score'] >= CONDITION_BATTLE_READY_MIN else 'BLOCKED'}")

# ── live/expired gates ──
gates = db.query(PRGate).filter(PRGate.user_id == user_id).all()
print(f"\nPR_GATES rows: {len(gates)}")
for g in gates:
    print(f"  {g.name} status={g.status} spawned={g.spawned_at} expires={g.expires_at}")

# ── replicate spawn rules per candidate lift (read-only) ──
now_d = datetime.now(timezone.utc).date()
print(f"\nSPAWN EVALUATION (max slots={MAX_OPEN_GATES_TOTAL}):")
lifts = _candidate_lifts(db, user_id)
if not lifts:
    print("  no candidate lifts (nothing matching STRENGTH_STANDARDS with e1RM sets)")
for lift in lifts:
    series = weekly_best_e1rm_series(db, user_id, lift["exercise_ids"])
    slope = weekly_slope(series)
    line = f"  {lift['name']:<28} weeks={len(series)}"
    if slope is None:
        print(line + "  → BLOCKED: <6 weeks of weekly-best e1RM data")
        continue
    last_week = series[-1][0]
    stale_days = (now_d - last_week).days
    line += f" slope={slope:+.2f} lb/wk last_week={last_week} ({stale_days}d ago)"
    if slope <= 0:
        print(line + "  → BLOCKED: slope not positive (not improving)")
        continue
    if stale_days > 14:
        print(line + "  → BLOCKED: stale (>14d since last trained week)")
        continue
    current = series[-1][1]
    projected = project_e1rm(current, slope, GATE_WINDOW_DAYS)
    baseline = lift["baseline"]
    need = baseline * SPAWN_MIN_FACTOR
    line += f" current={current:.0f} projected={projected:.0f} baseline={baseline:.0f} need>={need:.0f}"
    if projected < need:
        print(line + "  → BLOCKED: no PR projected inside window")
        continue
    low = need
    high = max(low, projected * TARGET_MAX_FACTOR)
    target = _select_target_set(low, high, _preferred_reps(db, user_id, lift["exercise_ids"]))
    if target is None:
        print(line + "  → BLOCKED: no plate-milestone target in range")
        continue
    print(line + f"  → WOULD SPAWN: target {target[0]:.0f}x{target[1]} (e1RM {target[2]:.0f})")

db.close()
