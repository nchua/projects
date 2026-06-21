"""
WHOOP API integration (Phase 1 wearable HR).

Implements the OAuth 2.0 Authorization Code flow against WHOOP and a post-workout
sync that backfills the app's WorkoutSession HR summary from WHOOP's workout
records. WHOOP's API is *post-workout only* — it returns a session-level summary
(avg/peak HR, strain, kJ) plus HR-zone durations, NOT raw per-second samples — so
this path populates session-level fields only. Per-set HR granularity is the
Apple Watch's job (Phase 2).

Because WHOOP HR arrives *after* the workout was logged (the create-time quest
path can't have seen it), ``sync_recent_workouts`` re-runs
``recalculate_quest_progress`` for each affected day so HR-based quests
(HR_ZONE_TIME / PEAK_HR / SESSION_STRAIN) get credited.

Credentials come from env vars (never hardcoded) — see ``app/core/config.py`` and
``docs/whoop-setup.md`` for how to register a WHOOP developer app. Tokens are
encrypted at rest on the WhoopConnection model (Fernet, ``app/core/crypto.py``).
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import httpx
from jose import JWTError, jwt
from sqlalchemy.orm import Session as DBSession

from app.core.config import settings
from app.core.utils import ensure_utc
from app.models.quest import UserQuest
from app.models.whoop import WhoopConnection
from app.models.workout import WorkoutSession
from app.services.quest_service import recalculate_quest_progress

logger = logging.getLogger(__name__)

# OAuth state is a short-lived signed JWT so the (unauthenticated) callback can
# recover which user started the flow without trusting the query string.
_STATE_PURPOSE = "whoop_oauth"
_STATE_TTL_MINUTES = 10

# Token is considered stale this many minutes before its real expiry so a sync
# never races the boundary.
_TOKEN_REFRESH_SKEW_MINUTES = 2

# When a session has no recorded duration, assume this length for time-overlap
# matching against a WHOOP workout.
_DEFAULT_SESSION_WINDOW_MINUTES = 90

# How far back to pull WHOOP workouts on a sync.
_DEFAULT_SYNC_DAYS = 30

_HTTP_TIMEOUT = 30.0

# WHOOP `zone_duration` milli fields -> our hr_zone_seconds keys. WHOOP zone_zero
# is the below-zone-1 (recovery) bucket; we keep it as z0 but the quest logic
# only counts z2-z5 as "elevated".
_ZONE_FIELD_MAP = {
    "zone_zero_milli": "z0",
    "zone_one_milli": "z1",
    "zone_two_milli": "z2",
    "zone_three_milli": "z3",
    "zone_four_milli": "z4",
    "zone_five_milli": "z5",
}


class WhoopError(Exception):
    """Generic WHOOP integration failure (OAuth or API)."""


class WhoopNotConfigured(WhoopError):
    """WHOOP client credentials are not set in the environment."""


class WhoopNotConnected(WhoopError):
    """The user has not connected their WHOOP account."""


# ── Config / connection helpers ──────────────────────────────────────────────

def is_configured() -> bool:
    """True when the WHOOP client credentials + redirect URI are all set."""
    return bool(
        settings.WHOOP_CLIENT_ID
        and settings.WHOOP_CLIENT_SECRET
        and settings.WHOOP_REDIRECT_URI
    )


def _require_configured() -> None:
    if not is_configured():
        raise WhoopNotConfigured(
            "WHOOP is not configured. Set WHOOP_CLIENT_ID, WHOOP_CLIENT_SECRET, "
            "and WHOOP_REDIRECT_URI (see docs/whoop-setup.md)."
        )


def get_connection(db: DBSession, user_id: str) -> Optional[WhoopConnection]:
    """Return the user's WHOOP connection, or None if not connected."""
    return (
        db.query(WhoopConnection)
        .filter(WhoopConnection.user_id == user_id)
        .first()
    )


# ── OAuth state ───────────────────────────────────────────────────────────────

def generate_oauth_state(user_id: str) -> str:
    """Sign a short-lived state token binding the OAuth flow to a user."""
    payload = {
        "sub": user_id,
        "purpose": _STATE_PURPOSE,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=_STATE_TTL_MINUTES),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_oauth_state(state: str) -> Optional[str]:
    """Validate a state token and return the user_id it was issued for."""
    if not state:
        return None
    try:
        payload = jwt.decode(state, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None
    if payload.get("purpose") != _STATE_PURPOSE:
        return None
    return payload.get("sub")


def get_authorize_url(user_id: str) -> str:
    """Build the WHOOP authorize URL to redirect the user to."""
    _require_configured()
    params = {
        "response_type": "code",
        "client_id": settings.WHOOP_CLIENT_ID,
        "redirect_uri": settings.WHOOP_REDIRECT_URI,
        "scope": settings.WHOOP_SCOPES,
        "state": generate_oauth_state(user_id),
    }
    return f"{settings.WHOOP_AUTH_URL}?{urlencode(params)}"


# ── Token exchange / refresh ──────────────────────────────────────────────────

def _token_request(grant_fields: Dict[str, str]) -> Dict[str, Any]:
    """POST to WHOOP's token endpoint with client credentials + grant fields."""
    _require_configured()
    data = {
        "client_id": settings.WHOOP_CLIENT_ID,
        "client_secret": settings.WHOOP_CLIENT_SECRET,
        **grant_fields,
    }
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        resp = client.post(
            settings.WHOOP_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if resp.status_code != 200:
        raise WhoopError(
            f"WHOOP token request failed ({resp.status_code}): {resp.text[:500]}"
        )
    return resp.json()


def _get_profile(access_token: str) -> Dict[str, Any]:
    """Fetch the WHOOP basic profile (for the WHOOP user_id)."""
    url = f"{settings.WHOOP_API_BASE_URL}/v1/user/profile/basic"
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        resp = client.get(url, headers={"Authorization": f"Bearer {access_token}"})
    if resp.status_code != 200:
        raise WhoopError(
            f"WHOOP profile request failed ({resp.status_code}): {resp.text[:500]}"
        )
    return resp.json()


def _apply_token(db: DBSession, conn: WhoopConnection, token: Dict[str, Any]) -> WhoopConnection:
    """Store an access/refresh token on the connection (encrypted) + refresh metadata."""
    access = token.get("access_token")
    if not access:
        raise WhoopError("WHOOP token response missing access_token.")
    conn.access_token = access
    # WHOOP only returns a refresh_token when the `offline` scope is granted;
    # don't wipe an existing one if a refresh response omits it.
    if token.get("refresh_token"):
        conn.refresh_token = token["refresh_token"]
    expires_in = int(token.get("expires_in", 3600))
    # Store naive UTC to match the rest of the schema (DB stores naive UTC).
    conn.expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    ).replace(tzinfo=None)
    if token.get("scope"):
        conn.scope = token["scope"]
    elif conn.scope is None:
        conn.scope = settings.WHOOP_SCOPES

    # Best-effort: capture the WHOOP user id. Don't fail the whole exchange if
    # the profile call hiccups — the tokens are still valid.
    try:
        profile = _get_profile(access)
        uid = profile.get("user_id")
        if uid is not None:
            conn.whoop_user_id = str(uid)
    except WhoopError as exc:
        logger.warning("WHOOP profile fetch failed during token store: %s", exc)

    db.flush()
    return conn


def exchange_code_for_token(db: DBSession, user_id: str, code: str) -> WhoopConnection:
    """Exchange an authorization code for tokens and persist the connection."""
    token = _token_request({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.WHOOP_REDIRECT_URI,
    })
    conn = get_connection(db, user_id)
    if conn is None:
        conn = WhoopConnection(user_id=user_id)
        db.add(conn)
    return _apply_token(db, conn, token)


def refresh_access_token(db: DBSession, conn: WhoopConnection) -> WhoopConnection:
    """Use the stored refresh token to obtain a fresh access token."""
    refresh = conn.refresh_token
    if not refresh:
        raise WhoopError("No WHOOP refresh token stored; the user must reconnect.")
    token = _token_request({
        "grant_type": "refresh_token",
        "refresh_token": refresh,
        # WHOOP wants the scope echoed on refresh; `offline` keeps rotating the
        # refresh token.
        "scope": settings.WHOOP_SCOPES,
    })
    return _apply_token(db, conn, token)


def _ensure_fresh_token(db: DBSession, conn: WhoopConnection) -> WhoopConnection:
    """Refresh the access token if it's missing or about to expire."""
    expires_at = ensure_utc(conn.expires_at)
    threshold = datetime.now(timezone.utc) + timedelta(minutes=_TOKEN_REFRESH_SKEW_MINUTES)
    if expires_at is None or expires_at <= threshold:
        refresh_access_token(db, conn)
    return conn


# ── WHOOP workout fetch ───────────────────────────────────────────────────────

def fetch_recent_workouts(
    access_token: str,
    start: Optional[datetime] = None,
    limit: int = 25,
    max_pages: int = 10,
) -> List[Dict[str, Any]]:
    """
    Pull recent WHOOP workout records (GET /v1/activity/workout), following
    pagination up to ``max_pages``. Returns the raw record dicts.
    """
    url = f"{settings.WHOOP_API_BASE_URL}/v1/activity/workout"
    base_params: Dict[str, Any] = {"limit": limit}
    if start is not None:
        base_params["start"] = (
            start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        )

    records: List[Dict[str, Any]] = []
    next_token: Optional[str] = None
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        for _ in range(max_pages):
            params = dict(base_params)
            if next_token:
                params["nextToken"] = next_token
            resp = client.get(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
            )
            if resp.status_code != 200:
                raise WhoopError(
                    f"WHOOP workout fetch failed ({resp.status_code}): {resp.text[:500]}"
                )
            body = resp.json()
            records.extend(body.get("records", []) or [])
            next_token = body.get("next_token")
            if not next_token:
                break
    return records


# ── Summary mapping + session matching ────────────────────────────────────────

def _zone_seconds_from_whoop(score: Dict[str, Any]) -> Dict[str, int]:
    """Convert WHOOP zone_duration milli fields to our {zN: seconds} map.

    Supports both v1 (`zone_duration`) and v2 (`zone_durations`) key names.
    """
    zones = score.get("zone_duration") or score.get("zone_durations") or {}
    result: Dict[str, int] = {}
    for whoop_key, app_key in _ZONE_FIELD_MAP.items():
        millis = zones.get(whoop_key)
        if millis is not None:
            result[app_key] = round(int(millis) / 1000)
    return result


def _parse_whoop_dt(value: Optional[str]) -> Optional[datetime]:
    """Parse a WHOOP ISO-8601 timestamp into an aware UTC datetime."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _session_window(session: WorkoutSession) -> Tuple[datetime, datetime]:
    """Aware-UTC [start, end] window for a session.

    A session logged at local midnight (date-only, no real clock time) is
    treated as spanning the whole day so a same-day WHOOP workout still matches.
    """
    start = ensure_utc(session.date)
    if start.hour == 0 and start.minute == 0 and start.second == 0:
        return start, start + timedelta(days=1)
    minutes = session.duration_minutes or _DEFAULT_SESSION_WINDOW_MINUTES
    return start, start + timedelta(minutes=minutes)


def _overlap_seconds(
    a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime
) -> float:
    """Seconds of overlap between two [start, end] intervals (0 if disjoint)."""
    latest_start = max(a_start, b_start)
    earliest_end = min(a_end, b_end)
    return max(0.0, (earliest_end - latest_start).total_seconds())


def _find_matching_session(
    sessions: List[WorkoutSession], whoop_start: datetime, whoop_end: datetime
) -> Optional[WorkoutSession]:
    """Pick the session with the greatest time overlap with the WHOOP workout."""
    best: Optional[WorkoutSession] = None
    best_overlap = 0.0
    for s in sessions:
        s_start, s_end = _session_window(s)
        overlap = _overlap_seconds(whoop_start, whoop_end, s_start, s_end)
        if overlap > best_overlap:
            best, best_overlap = s, overlap
    return best


def apply_whoop_summary(session: WorkoutSession, score: Dict[str, Any]) -> bool:
    """
    Backfill a session's HR summary from a WHOOP workout score.

    Non-destructive: only fills fields that are currently empty, so a re-sync is
    idempotent and a better source (Apple Watch) is never clobbered. Returns
    True if anything changed.
    """
    changed = False

    avg = score.get("average_heart_rate")
    if avg is not None and session.avg_heart_rate is None:
        session.avg_heart_rate = int(round(avg))
        changed = True

    peak = score.get("max_heart_rate")
    if peak is not None and session.peak_heart_rate is None:
        session.peak_heart_rate = int(round(peak))
        changed = True

    strain = score.get("strain")
    if strain is not None and session.strain is None:
        session.strain = float(strain)
        changed = True

    kj = score.get("kilojoule")
    if kj is not None and session.kilojoules is None:
        session.kilojoules = float(kj)
        changed = True

    zones = _zone_seconds_from_whoop(score)
    if zones and not session.hr_zone_seconds:
        session.hr_zone_seconds = zones
        changed = True

    if changed and session.hr_source is None:
        session.hr_source = "whoop"

    return changed


# ── Top-level sync ────────────────────────────────────────────────────────────

def sync_recent_workouts(
    db: DBSession, user_id: str, days: int = _DEFAULT_SYNC_DAYS
) -> Dict[str, Any]:
    """
    Pull recent WHOOP workouts and backfill matching app sessions' HR summaries,
    then re-credit HR-based quests for each affected day.

    The caller is responsible for committing the transaction.
    """
    conn = get_connection(db, user_id)
    if conn is None:
        raise WhoopNotConnected("WHOOP is not connected for this user.")
    _require_configured()
    _ensure_fresh_token(db, conn)

    start = datetime.now(timezone.utc) - timedelta(days=days)
    records = fetch_recent_workouts(conn.access_token, start=start)

    # Candidate sessions: the user's non-deleted sessions from slightly before
    # the sync window (a midnight-dated session can precede the WHOOP start).
    window_start = (start - timedelta(days=1)).replace(tzinfo=None)
    sessions = (
        db.query(WorkoutSession)
        .filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.deleted_at.is_(None),
            WorkoutSession.date >= window_start,
        )
        .all()
    )

    updated_session_ids: List[str] = []
    affected_dates = set()
    matched = 0
    unmatched = 0

    for rec in records:
        # Skip workouts WHOOP hasn't scored yet (no HR summary available).
        score_state = rec.get("score_state")
        if score_state is not None and score_state != "SCORED":
            continue
        score = rec.get("score") or {}
        if not score:
            continue

        whoop_start = _parse_whoop_dt(rec.get("start"))
        whoop_end = _parse_whoop_dt(rec.get("end"))
        if whoop_start is None or whoop_end is None:
            continue

        session = _find_matching_session(sessions, whoop_start, whoop_end)
        if session is None:
            unmatched += 1
            continue

        matched += 1
        if apply_whoop_summary(session, score):
            updated_session_ids.append(session.id)
            # Workout dates are LOCAL dates; coerce datetime -> date for the
            # quest-recalc lookup below.
            sd = session.date
            affected_dates.add(sd.date() if isinstance(sd, datetime) else sd)

    # HR arrives after the workout was logged, so the create-time quest path
    # never saw it — re-run the recalculation for every affected day so
    # HR_ZONE_TIME / PEAK_HR / SESSION_STRAIN quests get credited.
    completed_quest_ids: List[str] = []
    for d in affected_dates:
        unclaimed = (
            db.query(UserQuest)
            .filter(
                UserQuest.user_id == user_id,
                UserQuest.assigned_date == d,
                UserQuest.is_claimed.is_(False),
            )
            .all()
        )
        if unclaimed:
            completed_quest_ids.extend(
                recalculate_quest_progress(db, user_id, unclaimed, d)
            )

    conn.last_synced_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.flush()

    return {
        "workouts_fetched": len(records),
        "sessions_matched": matched,
        "sessions_updated": len(updated_session_ids),
        "workouts_unmatched": unmatched,
        "updated_session_ids": updated_session_ids,
        "quests_completed": completed_quest_ids,
    }
