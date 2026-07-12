"""
Hunter Condition — the 0-100 readiness score (ARISE v2 spec §4).

Computed on the fly (like ``exertion_score`` — never stored) from five inputs
that all already land in the DB: WHOOP recovery, muscle cooldowns, sleep,
yesterday's strain, and the resting-HR trend. Missing inputs are dropped and
the remaining weights renormalized (graceful degradation), so Condition never
comes up empty — muscle freshness is always computable.

Band thresholds and weights are module constants because Gate spawning
(Phase 2, spec §6.2) shares them: a Gate requires Condition >= BATTLE READY.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.exertion import compute_exertion_score
from app.core.utils import to_iso8601_utc
from app.models.activity import DailyActivity
from app.models.workout import WorkoutSession
from app.services.cooldown_service import COOLDOWN_TIMES, calculate_cooldowns

# Input weights (spec §4.1). Renormalized over available inputs only.
CONDITION_WEIGHTS: Dict[str, float] = {
    "recovery": 0.40,
    "cooldowns": 0.25,
    "sleep": 0.15,
    "strain_yesterday": 0.10,
    "rhr_trend": 0.10,
}

INPUT_LABELS: Dict[str, str] = {
    "recovery": "Recovery",
    "cooldowns": "Muscle Freshness",
    "sleep": "Sleep",
    "strain_yesterday": "Yesterday's Strain",
    "rhr_trend": "Resting HR Trend",
}

# Band thresholds (spec §4.2) — shared constants: Gates spawn only at
# BATTLE READY+ (>= CONDITION_BATTLE_READY_MIN) and the CRITICAL band forces
# a rest Directive (spec §5.2 rule 1).
CONDITION_PEAK_MIN = 85
CONDITION_BATTLE_READY_MIN = 65
CONDITION_STRAINED_MIN = 40

BAND_PEAK = "peak"
BAND_BATTLE_READY = "battle_ready"
BAND_STRAINED = "strained"
BAND_CRITICAL = "critical"

# Sleep normalization anchors: <=4 h scores 0, 7.5 h+ scores 100.
SLEEP_FLOOR_HOURS = 4.0
SLEEP_RANGE_HOURS = 3.5

# Strain normalization: strain <= 10 doesn't suppress Condition at all;
# 21 (max) maps to 40. Hard training is expected — only heavy strain counts.
STRAIN_NEUTRAL_MAX = 10.0
STRAIN_SCALE_MAX = 21.0
STRAIN_MIN_SUBSCORE = 40.0

# RHR trend: each bpm above the 14-day mean costs 10 points, floor 40.
RHR_LOOKBACK_DAYS = 14
RHR_POINTS_PER_BPM = 10.0
RHR_MIN_SUBSCORE = 40.0


def band_for_score(score: int) -> str:
    """Map a 0-100 Condition score to its band token (spec §4.2)."""
    if score >= CONDITION_PEAK_MIN:
        return BAND_PEAK
    if score >= CONDITION_BATTLE_READY_MIN:
        return BAND_BATTLE_READY
    if score >= CONDITION_STRAINED_MIN:
        return BAND_STRAINED
    return BAND_CRITICAL


def _source_badge(activity_source: Optional[str]) -> str:
    """Map a daily_activity.source value to a provenance badge token."""
    if activity_source and "whoop" in activity_source.lower():
        return "whoop"
    return "apple_watch"


def _pick_activity_value(
    rows: List[DailyActivity], attr: str
) -> Tuple[Optional[float], Optional[str]]:
    """Pick the first non-null value for ``attr`` across a day's activity rows.

    daily_activity is unique on (user_id, date, source), so one calendar day
    can hold several rows (apple_fitness + whoop_screenshot). WHOOP rows win
    because recovery/strain/sleep are WHOOP-native metrics.
    """
    ordered = sorted(
        rows, key=lambda r: 0 if "whoop" in (r.source or "").lower() else 1
    )
    for row in ordered:
        value = getattr(row, attr)
        if value is not None:
            return value, _source_badge(row.source)
    return None, None


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _freshness_subscore(muscles_cooling: List[Dict[str, Any]]) -> int:
    """Muscle-freshness sub-score over the 8 tracked muscles.

    The cooldown service reports ``cooldown_percent`` as percent *recovered*
    (100 = ready) and omits fully-ready muscles, so remaining fatigue per
    cooling muscle is ``100 - cooldown_percent`` and absent muscles contribute
    0 — the spec §4.1 "muscles absent count as fully fresh" rule.
    """
    remaining = sum(
        100.0 - float(m.get("cooldown_percent", 100.0))
        for m in muscles_cooling
        if m.get("status") == "cooling"
    )
    return round(_clamp(100.0 - remaining / len(COOLDOWN_TIMES)))


def _strain_subscore(strain: float) -> int:
    if strain <= STRAIN_NEUTRAL_MAX:
        return 100
    fraction = (strain - STRAIN_NEUTRAL_MAX) / (STRAIN_SCALE_MAX - STRAIN_NEUTRAL_MAX)
    return round(_clamp(100.0 - fraction * (100.0 - STRAIN_MIN_SUBSCORE),
                        STRAIN_MIN_SUBSCORE, 100.0))


def _yesterday_exertion(db: Session, user_id: str, yesterday: date) -> Optional[float]:
    """Max exertion score across yesterday's workouts (Apple-Watch fallback)."""
    day_start = datetime.combine(yesterday, datetime.min.time())
    day_end = day_start + timedelta(days=1)
    workouts = (
        db.query(WorkoutSession)
        .filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.deleted_at.is_(None),
            WorkoutSession.date >= day_start,
            WorkoutSession.date < day_end,
        )
        .all()
    )
    scores = [
        s for s in (compute_exertion_score(w.hr_zone_seconds) for w in workouts)
        if s is not None
    ]
    return max(scores) if scores else None


def compute_condition(
    db: Session,
    user_id: str,
    client_date: Optional[date] = None,
    user_age: Optional[int] = None,
) -> Dict[str, Any]:
    """Compute the Hunter Condition payload (spec §4.3 shape).

    Returns the full response dict: score, band, generated_at, per-input
    breakdown (with post-renormalization ``effective_weight``), and the
    ``muscles_cooling`` pass-through for the detail sheet.
    """
    today = client_date or date.today()
    yesterday = today - timedelta(days=1)

    today_rows = (
        db.query(DailyActivity)
        .filter(DailyActivity.user_id == user_id, DailyActivity.date == today)
        .all()
    )
    yesterday_rows = (
        db.query(DailyActivity)
        .filter(DailyActivity.user_id == user_id, DailyActivity.date == yesterday)
        .all()
    )

    # key -> (raw, subscore, source); subscore None = unavailable
    inputs: Dict[str, Tuple[Optional[float], Optional[int], Optional[str]]] = {}

    # 1. Recovery — WHOOP recovery_score, already 0-100. Badge is always
    # "whoop" regardless of which row carried it: recovery is WHOOP-native.
    recovery, _ = _pick_activity_value(today_rows, "recovery_score")
    inputs["recovery"] = (
        (float(recovery), round(_clamp(float(recovery))), "whoop")
        if recovery is not None else (None, None, None)
    )

    # 2. Muscle freshness — always available.
    cooldowns = calculate_cooldowns(db, user_id, user_age)
    muscles_cooling = cooldowns["muscles_cooling"]
    inputs["cooldowns"] = (None, _freshness_subscore(muscles_cooling), "app")

    # 3. Sleep.
    sleep_hours, sleep_src = _pick_activity_value(today_rows, "sleep_hours")
    if sleep_hours is not None:
        subscore = round(_clamp((float(sleep_hours) - SLEEP_FLOOR_HOURS)
                                / SLEEP_RANGE_HOURS, 0.0, 1.0) * 100.0)
        inputs["sleep"] = (float(sleep_hours), subscore, sleep_src)
    else:
        inputs["sleep"] = (None, None, None)

    # 4. Yesterday's strain — WHOOP day strain, else max workout exertion.
    strain, _ = _pick_activity_value(yesterday_rows, "strain")
    if strain is not None:
        inputs["strain_yesterday"] = (float(strain), _strain_subscore(float(strain)), "whoop")
    else:
        exertion = _yesterday_exertion(db, user_id, yesterday)
        if exertion is not None:
            inputs["strain_yesterday"] = (exertion, _strain_subscore(exertion), "apple_watch")
        else:
            inputs["strain_yesterday"] = (None, None, None)

    # 5. Resting-HR trend — today vs. 14-day mean.
    rhr_today, rhr_src = _pick_activity_value(today_rows, "resting_heart_rate")
    rhr_history = (
        db.query(DailyActivity.resting_heart_rate)
        .filter(
            DailyActivity.user_id == user_id,
            DailyActivity.date >= today - timedelta(days=RHR_LOOKBACK_DAYS),
            DailyActivity.date < today,
            DailyActivity.resting_heart_rate.isnot(None),
        )
        .all()
    )
    rhr_values = [row[0] for row in rhr_history]
    if rhr_today is not None and rhr_values:
        mean14 = sum(rhr_values) / len(rhr_values)
        subscore = round(_clamp(
            100.0 - RHR_POINTS_PER_BPM * max(0.0, float(rhr_today) - mean14),
            RHR_MIN_SUBSCORE, 100.0,
        ))
        inputs["rhr_trend"] = (float(rhr_today), subscore, rhr_src)
    else:
        inputs["rhr_trend"] = (None, None, None)

    # Renormalize over available inputs (spec §4.1 graceful degradation).
    available_weight = sum(
        CONDITION_WEIGHTS[key] for key, (_, sub, _) in inputs.items() if sub is not None
    )
    weighted_sum = sum(
        sub * CONDITION_WEIGHTS[key]
        for key, (_, sub, _) in inputs.items() if sub is not None
    )
    score = round(weighted_sum / available_weight) if available_weight > 0 else 0

    input_payload = []
    for key in CONDITION_WEIGHTS:
        raw, subscore, source = inputs[key]
        available = subscore is not None
        weight = CONDITION_WEIGHTS[key]
        input_payload.append({
            "key": key,
            "label": INPUT_LABELS[key],
            "raw": raw,
            "subscore": subscore,
            "weight": weight,
            "effective_weight": round(weight / available_weight, 4) if available else 0.0,
            "available": available,
            "source": source,
        })

    return {
        "score": score,
        "band": band_for_score(score),
        "generated_at": to_iso8601_utc(datetime.now(timezone.utc)),
        "inputs": input_payload,
        "muscles_cooling": muscles_cooling,
    }
