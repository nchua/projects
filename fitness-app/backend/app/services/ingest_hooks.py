"""
Ingest hook seam (ARISE v3 build, W0).

Every path that lands a ``WorkoutSession`` — ``POST /workouts``, ``POST /sync``,
the screenshot saves (``save_extracted_workout`` / ``save_whoop_activity``)
and the HealthKit import — calls :func:`on_workout_ingested` at least once per
session, after PR detection and XP, with the session **joined-loaded**
(``workout_exercises`` → ``sets`` / ``exercise``; see the CLAUDE.md joinedload
rule). The hook is the single place later workstreams attach to, so W1 and W2
never edit the ingest files in parallel:

* **W1** — ``campaign_service.link_session_to_plan(db, session,
  planned_hunt_id=...)`` links the session to the planned hunt on the same
  ``local_date`` (or the nearest same-type hunt within ±2 days → ``moved``)
  and returns ``{"planned_hunt_id", "planned_hunt_status"}`` for the create
  response (spec §4.4, §15.2).
* **W2** — ``training_load_service.recompute_daily_load(db, session.user_id,
  as_of=session.local_date)`` recomputes the trailing 35 days of
  ``daily_training_load`` (spec §6.2).

The orchestrator wires both in at the contract freeze; until then the hook
returns ``{}`` and callers merge nothing. Contract for the returned dict:
only ``planned_hunt_id`` (str | None) and ``planned_hunt_status`` (one of
``planned|done|modified|skipped|moved`` | None) are read by the ingest
endpoints; anything else is ignored.

Callers pass the session *before* their final ``db.commit()`` so the hook's
writes ride the same transaction. The hook must never raise for a missing
plan or missing load history — a free-form hunt is the common case.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models.workout import WorkoutSession


def on_workout_ingested(
    db: Session,
    session: WorkoutSession,
    *,
    planned_hunt_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Post-ingest hook. Returns a dict merged into the create response.

    Args:
        db: The ingest path's session (transaction owned by the caller).
        session: The persisted, joined-loaded ``WorkoutSession``.
        planned_hunt_id: The planned hunt the client says it was executing
            (``WorkoutCreate.planned_hunt_id``), if any.

    Returns:
        ``{}`` today. After the contract freeze: ``{"planned_hunt_id": ...,
        "planned_hunt_status": ...}`` from W1's linker (W2's load recompute
        contributes nothing to the response).
    """
    _ = (db, session, planned_hunt_id)
    return {}
