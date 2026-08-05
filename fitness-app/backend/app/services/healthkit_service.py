"""
Apple HealthKit (Apple Watch) workout import (Phase 2 wearable HR).

Implements the service behind ``POST /workouts/import-healthkit``: it accepts a
batch of completed ``HKWorkout``s (plus raw HR samples) read on-device, dedups by
HealthKit UUID, and routes each workout one of two ways:

* **Cardio / runs** (``is_strength == False``): builds a *synthetic*
  ``WorkoutSession`` inline (mirroring the WHOOP-activity session body, but
  without the DailyActivity/XP/PR side effects of ``save_whoop_activity``) and
  links it to the canonical Sport/Cardio exercise via the screenshot activity
  matcher.
* **Strength** (``is_strength == True``): finds the existing logged session that
  overlaps the workout in time (reusing the WHOOP time-overlap matchers) and
  *non-destructively* backfills its HR summary + per-set HR from the samples.

Unlike WHOOP, Apple Watch supplies raw per-second HR samples, so the strength
path can attribute HR to individual sets (via
``heart_rate_service.ingest_heart_rate``). HealthKit carries no ``strain``, so
``session_strain`` quests never credit from the Watch (expected).

Like ``whoop_service.sync_recent_workouts``, this service only ``db.flush()``es —
the **endpoint owns the final ``db.commit()``** (and rollback on error).

Datetime discipline: the DB stores **naive UTC**; the WHOOP overlap matchers
expect **aware UTC** (``ensure_utc``); ``ingest_heart_rate`` normalizes samples
to naive UTC itself. New session dates are stored naive-UTC so day-stat
helpers bucket them on the correct local day.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DBSession
from sqlalchemy.orm import joinedload

from app.core.utils import ensure_utc
from app.models.workout import WorkoutExercise, WorkoutSession
from app.schemas.healthkit import HealthKitWorkout
from app.services import screenshot_service
from app.services.heart_rate_service import ingest_heart_rate
from app.services.whoop_service import _find_matching_session

logger = logging.getLogger(__name__)

# HR provenance stamp for everything imported from Apple Health.
HR_SOURCE = "apple_watch"

# Pad the candidate-session query window on each side of the batch so a
# midnight-dated (date-only) session that precedes a workout's start can still
# be a match (mirrors whoop_service's window slack).
_CANDIDATE_WINDOW_PAD_DAYS = 1


def _to_naive_utc(dt: datetime) -> datetime:
    """Convert any (aware or naive) datetime to **naive UTC**.

    Schema-parsed ``start``/``end`` arrive tz-aware (``+00:00``); the DB stores
    naive UTC, so a session's ``date`` must be naive to compare cleanly against
    other rows and to bucket correctly in quest day-lookups.
    """
    aware = ensure_utc(dt)
    return aware.astimezone(timezone.utc).replace(tzinfo=None)


def _iso_utc(dt: datetime) -> str:
    """Format a datetime as a full ISO8601 UTC string with a trailing ``Z``.

    Used for the ``unmatched`` report items, where the client needs the real
    workout window (a plain ``to_iso8601_utc`` would collapse a midnight value
    to a date-only string and would not append ``Z`` for aware inputs).
    """
    return ensure_utc(dt).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _build_cardio_session(
    db: DBSession,
    user_id: str,
    workout: HealthKitWorkout,
) -> WorkoutSession:
    """Build + flush a synthetic cardio ``WorkoutSession`` for an Apple-Watch workout.

    Mirrors the session body created by ``screenshot_service.save_whoop_activity``
    (notes/duration/HR fields) but is intentionally inline so it does NOT trigger
    that function's DailyActivity / XP / PR writes. If the activity maps to a
    seeded Sport/Cardio exercise, a single exerciseless ``WorkoutExercise`` is
    attached so the workout shows up in exercise history.
    """
    notes_parts = [f"{workout.activity_type} - Apple Watch"]
    if workout.distance_meters is not None:
        # Kept in notes alongside the real column so older clients that
        # render notes still show the distance.
        notes_parts.append(f"Distance: {round(workout.distance_meters)}m")
    notes = " | ".join(notes_parts)

    session = WorkoutSession(
        user_id=user_id,
        date=_to_naive_utc(workout.start),
        duration_minutes=round(workout.duration_seconds / 60),
        hk_uuid=workout.hk_uuid,
        avg_heart_rate=workout.avg_heart_rate,
        peak_heart_rate=workout.peak_heart_rate,
        kilojoules=workout.kilojoules,
        hr_zone_seconds=workout.hr_zone_seconds,
        hr_source=HR_SOURCE,
        activity_type=workout.activity_type,
        distance_meters=workout.distance_meters,
        notes=notes,
    )
    db.add(session)
    db.flush()

    # Link to the canonical Sport/Cardio exercise when one matches (e.g.
    # "Outdoor Run" -> Running). Unknown activities (e.g. unseeded "Yoga")
    # produce an exerciseless session — still valid, just unlinked.
    exercise_id, exercise_name = screenshot_service.match_activity_to_exercise(
        db, workout.activity_type
    )
    if exercise_id:
        db.add(WorkoutExercise(
            session_id=session.id,
            exercise_id=exercise_id,
            order_index=0,
        ))
        db.flush()
        logger.info(
            "HealthKit cardio %r linked to exercise %r (id=%s)",
            workout.activity_type, exercise_name, exercise_id,
        )
    else:
        logger.info(
            "HealthKit cardio %r created exerciseless session (no sport match)",
            workout.activity_type,
        )

    return session


def _backfill_session_hr(session: WorkoutSession, workout: HealthKitWorkout) -> None:
    """Non-destructively backfill a matched session's HR summary from a workout.

    Only fills fields that are currently empty (so a re-import is idempotent and
    a better/earlier source is never clobbered), and only stamps ``hr_source``
    if it was unset — mirroring ``whoop_service.apply_whoop_summary``.
    """
    if workout.avg_heart_rate is not None and session.avg_heart_rate is None:
        session.avg_heart_rate = int(workout.avg_heart_rate)
    if workout.peak_heart_rate is not None and session.peak_heart_rate is None:
        session.peak_heart_rate = int(workout.peak_heart_rate)
    if workout.kilojoules is not None and session.kilojoules is None:
        session.kilojoules = float(workout.kilojoules)
    if workout.hr_zone_seconds and not session.hr_zone_seconds:
        session.hr_zone_seconds = workout.hr_zone_seconds
    if session.hr_source is None:
        session.hr_source = HR_SOURCE


def import_healthkit_workouts(
    db: DBSession,
    user_id: str,
    workouts: List[HealthKitWorkout],
) -> Dict[str, Any]:
    """Import a batch of Apple-Watch workouts, dedup, route, and recredit quests.

    Steps (per the Chunk A spec):
      1. **Dedup** against existing non-null ``hk_uuid``s for the user (and
         intra-batch duplicates) -> ``skipped_duplicates``.
      2. **Cardio** -> build a synthetic session inline -> ``sessions_created``.
      3. **Strength** -> match an existing session by time overlap, backfill HR
         non-destructively, attribute raw samples to sets -> ``sessions_updated``;
         no match -> ``unmatched`` (session NOT created, ``hk_uuid`` NOT consumed).

    Only ``db.flush()``es; the **caller (endpoint) owns ``db.commit()``** (and
    rollback). Returns a dict with exactly these keys::

        {"imported", "skipped_duplicates", "sessions_created",
         "sessions_updated", "unmatched", "quests_completed"}

    where each ``unmatched`` item is
    ``{"hk_uuid", "activity_type", "start", "end"}`` (ISO8601-UTC strings).

    Args:
        db: Database session (transaction owned by the caller).
        user_id: The authenticated user's id.
        workouts: Validated ``HealthKitWorkout`` batch (already bounded 1..100
            by the request schema).

    Returns:
        The import-result dict described above.
    """
    imported: List[str] = []
    skipped_duplicates: List[str] = []
    sessions_created: List[str] = []
    sessions_updated: List[str] = []
    unmatched: List[Dict[str, str]] = []

    # ── 1. Dedup set: existing hk_uuids for this user + intra-batch dups ──
    known_uuids = {
        row[0]
        for row in db.query(WorkoutSession.hk_uuid)
        .filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.hk_uuid.isnot(None),
        )
        .all()
    }

    # ── Lazily load candidate sessions for the strength path (once) ──
    candidate_sessions: Optional[List[WorkoutSession]] = None

    def _load_candidate_sessions() -> List[WorkoutSession]:
        """Load the user's non-deleted sessions in a padded window around the batch."""
        starts = [_to_naive_utc(w.start) for w in workouts]
        ends = [_to_naive_utc(w.end) for w in workouts]
        window_start = min(starts) - timedelta(days=_CANDIDATE_WINDOW_PAD_DAYS)
        window_end = max(ends) + timedelta(days=_CANDIDATE_WINDOW_PAD_DAYS)
        return (
            db.query(WorkoutSession)
            .filter(
                WorkoutSession.user_id == user_id,
                WorkoutSession.deleted_at.is_(None),
                # Only attach to sessions not already linked to a HealthKit
                # workout, so a new HK workout never clobbers an existing
                # session's hk_uuid (which would drop a dedup key and let a
                # later re-import duplicate HR samples).
                WorkoutSession.hk_uuid.is_(None),
                WorkoutSession.date >= window_start,
                WorkoutSession.date <= window_end,
            )
            .all()
        )

    for workout in workouts:
        hk_uuid = workout.hk_uuid

        # 1. Dedup (existing rows OR an earlier item in this same batch).
        if hk_uuid in known_uuids:
            skipped_duplicates.append(hk_uuid)
            continue
        known_uuids.add(hk_uuid)

        if not workout.is_strength:
            # ── 2. Cardio path ──
            session = _build_cardio_session(db, user_id, workout)
            sessions_created.append(session.id)
            imported.append(hk_uuid)

            # Persist raw cardio samples (no sets -> all set_id=None) so the
            # series is available even though there's no per-set attribution.
            if workout.heart_rate_samples:
                ingest_heart_rate(
                    db, session, workout.heart_rate_samples, source=HR_SOURCE
                )
            continue

        # ── 3. Strength path: match an existing logged session by overlap ──
        if candidate_sessions is None:
            candidate_sessions = _load_candidate_sessions()

        match = _find_matching_session(
            candidate_sessions,
            ensure_utc(workout.start),
            ensure_utc(workout.end),
        )
        if match is None:
            # No overlapping session: report it, create nothing, and do NOT
            # consume the hk_uuid (remove it from `known_uuids` so a later
            # re-import can attach once the lift is logged).
            known_uuids.discard(hk_uuid)
            unmatched.append({
                "hk_uuid": hk_uuid,
                "activity_type": workout.activity_type,
                "start": _iso_utc(workout.start),
                "end": _iso_utc(workout.end),
            })
            continue

        # One session ↔ one HK workout per batch: remove the matched session
        # from the candidate pool so a second strength workout overlapping the
        # same session can't re-match it (which would overwrite hk_uuid, double
        # the sessions_updated entry, and lose a dedup key). The second workout
        # then falls through to `unmatched` — correct, it has no free session.
        candidate_sessions.remove(match)

        # Match: stamp the uuid + backfill HR non-destructively.
        match.hk_uuid = hk_uuid
        _backfill_session_hr(match, workout)
        db.flush()
        sessions_updated.append(match.id)
        imported.append(hk_uuid)

        # Per-set HR attribution: re-query with joinedload(exercises->sets) so
        # the relationship collections are populated before ingest_heart_rate
        # walks them (CLAUDE.md joinedload rule — collections are empty right
        # after a flush otherwise).
        if workout.heart_rate_samples:
            hydrated = (
                db.query(WorkoutSession)
                .options(
                    joinedload(WorkoutSession.workout_exercises)
                    .joinedload(WorkoutExercise.sets)
                )
                .filter(WorkoutSession.id == match.id)
                .first()
            )
            if hydrated is not None:
                ingest_heart_rate(
                    db, hydrated, workout.heart_rate_samples, source=HR_SOURCE
                )

    # Daily quests were removed in ARISE v2 Phase 0; the response keeps the
    # ``quests_completed`` key (always empty) so the client contract is stable.
    quests_completed: List[str] = []

    db.flush()

    return {
        "imported": imported,
        "skipped_duplicates": skipped_duplicates,
        "sessions_created": sessions_created,
        "sessions_updated": sessions_updated,
        "unmatched": unmatched,
        "quests_completed": quests_completed,
    }
