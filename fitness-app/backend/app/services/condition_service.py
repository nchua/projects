"""
Hunter Condition — the 0-100 readiness score (ARISE v2 spec §4, v3 §6.5).

Computed on the fly (like ``exertion_score`` — never stored) from six inputs
that all already land in the DB: WHOOP recovery, muscle cooldowns, sleep,
the acute-vs-chronic training-load ratio, the resting-HR trend and the HRV
trend. Missing inputs are dropped and the remaining weights renormalized
(graceful degradation), so Condition never comes up empty — muscle freshness
is always computable.

v3 (§6.5): input 4 "yesterday's strain" became the **training-load ratio**
(``total_acwr`` from ``training_load_service``; unavailable until 28 days of
history), and **HRV trend** was added as input 6 — when it is present,
recovery's weight drops 0.40 → 0.30 so the weights still sum to 1.

Band thresholds and weights are module constants because Gate spawning
(spec §6.2) shares them: a Gate requires Condition >= BATTLE READY.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.utils import to_iso8601_utc
from app.models.activity import DailyActivity
from app.services.cooldown_service import COOLDOWN_TIMES, calculate_cooldowns
from app.services.training_load_service import get_load_state

# Input weights (spec §4.1 / v3 §6.5). Renormalized over available inputs only.
# ``recovery`` is 0.40 when HRV trend is unavailable and
# RECOVERY_WEIGHT_WITH_HRV when it is present (both sum to 1.0).
CONDITION_WEIGHTS: Dict[str, float] = {
    "recovery": 0.40,
    "cooldowns": 0.25,
    "sleep": 0.15,
    "load_ratio": 0.10,
    "rhr_trend": 0.10,
    "hrv_trend": 0.10,
}
RECOVERY_WEIGHT_WITH_HRV = 0.30

INPUT_LABELS: Dict[str, str] = {
    "recovery": "Recovery",
    "cooldowns": "Muscle Freshness",
    "sleep": "Sleep",
    "load_ratio": "Training Load",
    "rhr_trend": "Resting HR Trend",
    "hrv_trend": "HRV Trend",
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

# Training-load ratio (v3 §6.5): acute/chronic total load <= 1.0 doesn't
# suppress Condition at all; 1.5 maps to 40 (floor). Hard weeks are expected —
# only load that outruns fitness counts.
LOAD_RATIO_NEUTRAL_MAX = 1.0
LOAD_RATIO_FLOOR_AT = 1.5
LOAD_RATIO_MIN_SUBSCORE = 40.0

# RHR trend: each bpm above the 14-day mean costs 10 points, floor 40.
RHR_LOOKBACK_DAYS = 14
RHR_POINTS_PER_BPM = 10.0
RHR_MIN_SUBSCORE = 40.0

# HRV trend (v3 §6.5): 7-day mean vs 28-day mean; subscore
# 100 − 300 × max(0, 1 − ratio), floor 40. Needs enough days in both windows.
HRV_SHORT_DAYS = 7
HRV_LONG_DAYS = 28
HRV_MIN_SHORT_DAYS = 4
HRV_MIN_LONG_DAYS = 10
HRV_POINTS_PER_UNIT_DROP = 300.0
HRV_MIN_SUBSCORE = 40.0


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


def _whoop_first(rows: List[DailyActivity]) -> List[DailyActivity]:
    """Order a day's activity rows WHOOP-first (WHOOP-native metrics win)."""
    return sorted(rows, key=lambda r: 0 if "whoop" in (r.source or "").lower() else 1)


def _pick_activity_value(
    rows: List[DailyActivity], attr: str
) -> Tuple[Optional[float], Optional[str]]:
    """Pick the first non-null value for ``attr`` across a day's activity rows.

    daily_activity is unique on (user_id, date, source), so one calendar day
    can hold several rows (apple_fitness + whoop_screenshot). WHOOP rows win
    because recovery/strain/sleep are WHOOP-native metrics.
    """
    for row in _whoop_first(rows):
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


def _load_ratio_subscore(ratio: float) -> int:
    """100 at ratio <= 1.0, linear to 40 at 1.5, floor 40 (v3 §6.5)."""
    if ratio <= LOAD_RATIO_NEUTRAL_MAX:
        return 100
    fraction = (ratio - LOAD_RATIO_NEUTRAL_MAX) / (LOAD_RATIO_FLOOR_AT - LOAD_RATIO_NEUTRAL_MAX)
    return round(_clamp(
        100.0 - fraction * (100.0 - LOAD_RATIO_MIN_SUBSCORE),
        LOAD_RATIO_MIN_SUBSCORE, 100.0,
    ))


def _hrv_subscore(ratio: float) -> int:
    """100 − 300 × max(0, 1 − ratio), floor 40 (v3 §6.5)."""
    return round(_clamp(
        100.0 - HRV_POINTS_PER_UNIT_DROP * max(0.0, 1.0 - ratio),
        HRV_MIN_SUBSCORE, 100.0,
    ))


def _hrv_trend(
    db: Session, user_id: str, today: date
) -> Tuple[Optional[float], Optional[str]]:
    """7-day mean vs 28-day mean of ``DailyActivity.hrv`` → (ratio, badge).

    One value per day (WHOOP rows preferred); needs >= HRV_MIN_SHORT_DAYS
    days in the last 7 and >= HRV_MIN_LONG_DAYS in the last 28, else
    unavailable. The badge follows the most recent HRV day's row source.
    """
    long_start = today - timedelta(days=HRV_LONG_DAYS - 1)
    short_start = today - timedelta(days=HRV_SHORT_DAYS - 1)
    rows = (
        db.query(DailyActivity)
        .filter(
            DailyActivity.user_id == user_id,
            DailyActivity.date >= long_start,
            DailyActivity.date <= today,
            DailyActivity.hrv.isnot(None),
        )
        .all()
    )
    by_day: Dict[date, List[DailyActivity]] = {}
    for row in rows:
        by_day.setdefault(row.date, []).append(row)

    daily: Dict[date, Tuple[float, str]] = {}
    for day, day_rows in by_day.items():
        value, badge = _pick_activity_value(day_rows, "hrv")
        if value is not None:
            daily[day] = (float(value), badge or "apple_watch")

    long_values = [v for _, (v, _) in daily.items()]
    short_values = [v for d, (v, _) in daily.items() if d >= short_start]
    if len(short_values) < HRV_MIN_SHORT_DAYS or len(long_values) < HRV_MIN_LONG_DAYS:
        return None, None
    long_mean = sum(long_values) / len(long_values)
    if long_mean <= 0:
        return None, None
    ratio = (sum(short_values) / len(short_values)) / long_mean
    latest_day = max(daily)
    return round(ratio, 3), daily[latest_day][1]


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

    today_rows = (
        db.query(DailyActivity)
        .filter(DailyActivity.user_id == user_id, DailyActivity.date == today)
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

    # 4. Training-load ratio — acute vs chronic total load (v3 §6.5).
    # Unavailable (renormalized away) until 28 days of history.
    load_ratio = get_load_state(db, user_id, today).get("total_acwr")
    if load_ratio is not None:
        inputs["load_ratio"] = (float(load_ratio), _load_ratio_subscore(float(load_ratio)), "app")
    else:
        inputs["load_ratio"] = (None, None, None)

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

    # 6. HRV trend — 7-day mean vs 28-day mean (v3 §6.5).
    hrv_ratio, hrv_src = _hrv_trend(db, user_id, today)
    if hrv_ratio is not None:
        inputs["hrv_trend"] = (hrv_ratio, _hrv_subscore(hrv_ratio), hrv_src)
    else:
        inputs["hrv_trend"] = (None, None, None)

    # Weights: recovery yields 0.10 to HRV trend when it is present (§6.5).
    weights = dict(CONDITION_WEIGHTS)
    if inputs["hrv_trend"][1] is not None:
        weights["recovery"] = RECOVERY_WEIGHT_WITH_HRV

    # Renormalize over available inputs (spec §4.1 graceful degradation).
    available_weight = sum(
        weights[key] for key, (_, sub, _) in inputs.items() if sub is not None
    )
    weighted_sum = sum(
        sub * weights[key]
        for key, (_, sub, _) in inputs.items() if sub is not None
    )
    score = round(weighted_sum / available_weight) if available_weight > 0 else 0

    input_payload = []
    for key in CONDITION_WEIGHTS:
        raw, subscore, source = inputs[key]
        available = subscore is not None
        weight = weights[key]
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
