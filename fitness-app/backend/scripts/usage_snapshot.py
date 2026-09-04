"""Read-only prod usage snapshot (companion to gate_diagnostic.py).

Run from fitness-app/backend: venv/bin/python scripts/usage_snapshot.py

Opens the Railway Postgres in a READ ONLY transaction, picks the primary
user (most workout sessions), and prints aggregate behaviour only. Never
prints emails, tokens, or row-level notes.
"""
from __future__ import annotations

import os
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
url = os.environ.get("DATABASE_URL", "")
if not url:
    sys.exit("DATABASE_URL not set")

engine = create_engine(url, connect_args={"options": "-c default_transaction_read_only=on"})


def q(sql: str, **params):
    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        return conn.execute(text(sql), params).fetchall()


def section(title: str) -> None:
    print(f"\n=== {title} ===")


# ── users ──
section("USERS")
rows = q("SELECT count(*) AS n, sum(CASE WHEN is_deleted THEN 1 ELSE 0 END) AS deleted FROM users")
print(f"users total={rows[0][0]} deleted={rows[0][1]}")
rows = q(
    """SELECT user_id, count(*) AS n, min(date), max(date)
       FROM workout_sessions WHERE deleted_at IS NULL
       GROUP BY user_id ORDER BY n DESC LIMIT 5"""
)
for r in rows:
    print(f"  user …{str(r[0])[-4:]}: sessions={r[1]} first={r[2].date() if r[2] else None} last={r[3].date() if r[3] else None}")
UID = rows[0][0]
print(f"primary user chosen: …{UID[-4:]}")

# ── progress ──
section("PROGRESS")
r = q("SELECT level, rank, total_xp, current_streak, longest_streak, last_workout_date, total_workouts, total_prs FROM user_progress WHERE user_id=:u", u=UID)
print(r[0] if r else "none")

# ── sessions by week, split strength/cardio, last 20 weeks ──
section("SESSIONS BY ISO WEEK (last 20 weeks)")
rows = q(
    """SELECT s.id, s.date, s.activity_type, s.distance_meters, s.duration_minutes, s.hr_source,
              s.hk_uuid IS NOT NULL AS from_hk, s.client_id IS NOT NULL AS has_client_id,
              s.avg_heart_rate, s.strain, s.name,
              (SELECT count(*) FROM workout_exercises we JOIN sets st ON st.workout_exercise_id=we.id WHERE we.session_id=s.id) AS n_sets,
              (SELECT count(*) FROM workout_exercises we WHERE we.session_id=s.id) AS n_ex
       FROM workout_sessions s
       WHERE s.user_id=:u AND s.deleted_at IS NULL AND s.date >= :since
       ORDER BY s.date""",
    u=UID, since=datetime.utcnow() - timedelta(weeks=20),
)
weeks: dict = defaultdict(lambda: Counter())
src = Counter()
kinds = Counter()
for r in rows:
    d = r[1]
    iso = d.isocalendar()
    key = f"{iso[0]}-W{iso[1]:02d}"
    is_cardio = bool(r[2]) or (r[3] or 0) > 0
    has_sets = (r[11] or 0) > 0
    kind = "cardio" if is_cardio and not has_sets else ("strength" if has_sets else "other")
    weeks[key][kind] += 1
    if kind == "cardio":
        weeks[key]["miles"] += (r[3] or 0) / 1609.34
    src[(("hk" if r[6] else "app") , r[5] or "none")] += 1
    kinds[kind] += 1
for k in sorted(weeks):
    c = weeks[k]
    print(f"  {k}: strength={c['strength']} cardio={c['cardio']} other={c['other']} miles={c['miles']:.1f}")
print("kinds:", dict(kinds))
print("source (hk/app, hr_source):", dict(src))

# ── strength sessions detail: exercises frequency last 12 weeks ──
section("TOP EXERCISES (last 12 weeks, strength sessions)")
rows = q(
    """SELECT e.name, count(DISTINCT s.id) AS sessions, count(st.id) AS sets,
              max(st.e1rm) AS best_e1rm,
              sum(CASE WHEN st.rpe IS NOT NULL THEN 1 ELSE 0 END) AS sets_with_rpe,
              sum(CASE WHEN st.avg_heart_rate IS NOT NULL THEN 1 ELSE 0 END) AS sets_with_hr
       FROM workout_sessions s
       JOIN workout_exercises we ON we.session_id=s.id
       JOIN sets st ON st.workout_exercise_id=we.id
       JOIN exercises e ON e.id=we.exercise_id
       WHERE s.user_id=:u AND s.deleted_at IS NULL AND s.date >= :since
       GROUP BY e.name ORDER BY sessions DESC, sets DESC LIMIT 20""",
    u=UID, since=datetime.utcnow() - timedelta(weeks=12),
)
for r in rows:
    print(f"  {r[0]:<32} sessions={r[1]:<3} sets={r[2]:<4} best_e1rm={round(r[3] or 0):<5} rpe={r[4]} hr={r[5]}")

# ── weekly best e1rm series for big three (last 16 weeks) ──
section("WEEKLY BEST e1RM — big three (last 16 weeks)")
for kw in ("squat", "bench", "deadlift"):
    rows = q(
        """SELECT date_trunc('week', s.date)::date AS wk, max(st.e1rm) AS best, count(st.id) AS sets
           FROM workout_sessions s
           JOIN workout_exercises we ON we.session_id=s.id
           JOIN sets st ON st.workout_exercise_id=we.id
           JOIN exercises e ON e.id=we.exercise_id
           WHERE s.user_id=:u AND s.deleted_at IS NULL AND s.date >= :since
             AND lower(e.name) LIKE :kw
           GROUP BY wk ORDER BY wk""",
        u=UID, since=datetime.utcnow() - timedelta(weeks=16), kw=f"%{kw}%",
    )
    series = ", ".join(f"{r[0].strftime('%m/%d')}:{round(r[1] or 0)}({r[2]})" for r in rows)
    print(f"  {kw:<9} weeks_with_data={len(rows)}  {series}")

# ── session duration + name usage ──
section("SESSION META (last 12 weeks)")
rows = q(
    """SELECT count(*), avg(duration_minutes), sum(CASE WHEN name IS NOT NULL THEN 1 ELSE 0 END),
              sum(CASE WHEN session_rpe IS NOT NULL THEN 1 ELSE 0 END),
              sum(CASE WHEN notes IS NOT NULL AND notes<>'' THEN 1 ELSE 0 END),
              sum(CASE WHEN avg_heart_rate IS NOT NULL THEN 1 ELSE 0 END),
              sum(CASE WHEN strain IS NOT NULL THEN 1 ELSE 0 END),
              sum(CASE WHEN mile_splits IS NOT NULL THEN 1 ELSE 0 END)
       FROM workout_sessions WHERE user_id=:u AND deleted_at IS NULL AND date >= :since""",
    u=UID, since=datetime.utcnow() - timedelta(weeks=12),
)
r = rows[0]
print(f"sessions={r[0]} avg_dur_min={round(r[1] or 0)} named={r[2]} session_rpe={r[3]} notes={r[4]} with_avg_hr={r[5]} with_whoop_strain={r[6]} with_splits={r[7]}")

# ── gates / directives ──
section("GATES")
rows = q("SELECT status, count(*) FROM pr_gates WHERE user_id=:u GROUP BY status", u=UID)
print(dict((r[0], r[1]) for r in rows) or "no gates ever")
rows = q("SELECT name, rank, status, spawned_at::date, expires_at::date, baseline_e1rm, target_e1rm FROM pr_gates WHERE user_id=:u ORDER BY spawned_at DESC LIMIT 5", u=UID)
for r in rows:
    print("  ", r)

section("DIRECTIVES (all time)")
rows = q(
    """SELECT directive_type, count(*), sum(CASE WHEN is_completed THEN 1 ELSE 0 END), min(date), max(date)
       FROM user_directives WHERE user_id=:u GROUP BY directive_type ORDER BY 2 DESC""",
    u=UID,
)
for r in rows:
    print(f"  {r[0]:<16} generated={r[1]:<4} completed={r[2]:<4} {r[3]}..{r[4]}")
rows = q("SELECT count(DISTINCT date) FROM user_directives WHERE user_id=:u AND date >= :since", u=UID, since=date.today() - timedelta(days=28))
print(f"distinct app-open days with a directive in last 28d: {rows[0][0]}")

# ── daily activity coverage last 30 days ──
section("DAILY ACTIVITY COVERAGE (last 30 days)")
rows = q(
    """SELECT source, count(DISTINCT date),
              sum(CASE WHEN steps IS NOT NULL THEN 1 ELSE 0 END),
              sum(CASE WHEN sleep_hours IS NOT NULL THEN 1 ELSE 0 END),
              sum(CASE WHEN hrv IS NOT NULL THEN 1 ELSE 0 END),
              sum(CASE WHEN resting_heart_rate IS NOT NULL THEN 1 ELSE 0 END),
              sum(CASE WHEN recovery_score IS NOT NULL THEN 1 ELSE 0 END),
              sum(CASE WHEN strain IS NOT NULL THEN 1 ELSE 0 END)
       FROM daily_activity WHERE user_id=:u AND date >= :since GROUP BY source""",
    u=UID, since=date.today() - timedelta(days=30),
)
for r in rows:
    print(f"  {r[0]:<18} days={r[1]:<3} steps={r[2]} sleep={r[3]} hrv={r[4]} rhr={r[5]} recovery={r[6]} strain={r[7]}")
rows = q("SELECT max(date) FROM daily_activity WHERE user_id=:u", u=UID)
print("latest daily_activity date:", rows[0][0])

# ── integrations ──
section("INTEGRATIONS / MISC")
r = q("SELECT count(*), max(last_synced_at) FROM whoop_connections WHERE user_id=:u", u=UID)[0]
print(f"whoop_connection rows={r[0]} last_synced={r[1]}")
r = q(
    "SELECT count(*) FROM device_tokens WHERE is_active AND user_id = :u",
    u=UID,
)[0]
print(f"active device tokens={r[0]}")
r = q("SELECT status, count(*) FROM goals WHERE user_id=:u GROUP BY status", u=UID)
print("goals:", dict((x[0], x[1]) for x in r) or "none")
r = q("SELECT count(*), max(date) FROM bodyweight_entries WHERE user_id=:u", u=UID)[0]
print(f"bodyweight entries={r[0]} last={r[1]}")
r = q("SELECT scan_credits, has_unlimited FROM scan_balances WHERE user_id=:u", u=UID)
print("scan balance:", r[0] if r else "none")
r = q("SELECT count(*) FROM prs WHERE user_id=:u AND achieved_at >= :since", u=UID, since=datetime.utcnow() - timedelta(weeks=12))[0]
print(f"PRs last 12 weeks={r[0]}")
r = q("SELECT count(*) FROM screenshot_usage WHERE user_id=:u AND created_at >= :since", u=UID, since=datetime.utcnow() - timedelta(weeks=12))[0]
print(f"screenshot scans last 12 weeks={r[0]}")
r = q("SELECT count(*), sum(CASE WHEN is_custom THEN 1 ELSE 0 END) FROM exercises")[0]
print(f"exercise library={r[0]} custom={r[1]}")
r = q("SELECT count(*) FROM user_achievements WHERE user_id=:u", u=UID)[0]
print(f"achievements unlocked={r[0]}")

# ── run detail last 8 weeks ──
section("RUNS (last 8 weeks)")
rows = q(
    """SELECT date::date, activity_type, round((distance_meters/1609.34)::numeric,2), duration_seconds, avg_heart_rate, mile_splits IS NOT NULL
       FROM workout_sessions WHERE user_id=:u AND deleted_at IS NULL AND distance_meters IS NOT NULL AND date >= :since ORDER BY date""",
    u=UID, since=datetime.utcnow() - timedelta(weeks=8),
)
for r in rows:
    pace = (r[3] / 60) / float(r[2]) if r[3] and r[2] and float(r[2]) > 0 else None
    print(f"  {r[0]} {r[1]:<14} {r[2]} mi  {round(r[3]/60) if r[3] else '?'} min  pace={round(pace,1) if pace else '?'} hr={r[4]} splits={r[5]}")
