"""
Tests for Condition v2 (ARISE v3 spec §6.5).

Input 4 is now the acute-vs-chronic training-load ratio (unavailable until
28 days of history); input 6 is the HRV trend (7-day vs 28-day mean), whose
presence moves recovery's weight from 0.40 to 0.30 so the table still sums
to 1. Both are exercised with and without their data, and the renormalized
weights are checked to sum to 1 in every configuration.
"""
import uuid
from datetime import date, timedelta

from app.models.activity import DailyActivity
from app.services import condition_service
from app.services.condition_service import (
    CONDITION_WEIGHTS,
    RECOVERY_WEIGHT_WITH_HRV,
    _hrv_subscore,
    _load_ratio_subscore,
    compute_condition,
)

TODAY = date(2026, 9, 5)


def _user(create_test_user):
    return create_test_user(email=f"cond2-{uuid.uuid4().hex[:8]}@example.com")[0]


def _activity(db, user_id, day, source="whoop_screenshot", **fields):
    db.add(DailyActivity(user_id=user_id, date=day, source=source, **fields))
    db.commit()


def _patch_load(monkeypatch, total_acwr):
    monkeypatch.setattr(
        condition_service, "get_load_state",
        lambda db, user_id, as_of: {"total_acwr": total_acwr},
    )


def _by_key(result):
    return {i["key"]: i for i in result["inputs"]}


# ── Formulas ────────────────────────────────────────────────────────────────

def test_load_ratio_subscore_formula():
    assert _load_ratio_subscore(0.6) == 100
    assert _load_ratio_subscore(1.0) == 100
    assert _load_ratio_subscore(1.25) == 70     # midpoint of the 1.0 → 1.5 ramp
    assert _load_ratio_subscore(1.5) == 40
    assert _load_ratio_subscore(2.4) == 40      # floor


def test_hrv_subscore_formula():
    assert _hrv_subscore(1.2) == 100            # improving HRV never boosts past 100
    assert _hrv_subscore(1.0) == 100
    assert _hrv_subscore(0.9) == 70             # 100 − 300 × 0.1
    assert _hrv_subscore(0.8) == 40
    assert _hrv_subscore(0.5) == 40             # floor


def test_base_weights_sum_to_one_in_both_configurations():
    without_hrv = sum(w for k, w in CONDITION_WEIGHTS.items() if k != "hrv_trend")
    with_hrv = sum(CONDITION_WEIGHTS.values()) - CONDITION_WEIGHTS["recovery"] + RECOVERY_WEIGHT_WITH_HRV
    assert round(without_hrv, 6) == 1.0
    assert round(with_hrv, 6) == 1.0


# ── Training-load ratio (input 4) ───────────────────────────────────────────

def test_load_ratio_unavailable_before_28_days(db, create_test_user, monkeypatch):
    user = _user(create_test_user)
    _patch_load(monkeypatch, None)
    inputs = _by_key(compute_condition(db, user.id, TODAY))
    assert inputs["load_ratio"]["available"] is False
    assert inputs["load_ratio"]["effective_weight"] == 0.0
    assert inputs["load_ratio"]["label"] == "Training Load"


def test_load_ratio_present_scores_and_badges_app(db, create_test_user, monkeypatch):
    user = _user(create_test_user)
    _patch_load(monkeypatch, 1.25)
    result = compute_condition(db, user.id, TODAY)
    inputs = _by_key(result)
    assert inputs["load_ratio"]["available"] is True
    assert inputs["load_ratio"]["raw"] == 1.25
    assert inputs["load_ratio"]["subscore"] == 70
    assert inputs["load_ratio"]["source"] == "app"
    assert inputs["load_ratio"]["weight"] == 0.10
    # cooldowns (0.25, 100) + load_ratio (0.10, 70) → (25 + 7) / 0.35 ≈ 91
    assert result["score"] == 91


def test_load_ratio_reads_the_real_load_state(db, create_test_user):
    """Without a patch the ratio comes from training_load_service (no
    history → unavailable, never an error)."""
    user = _user(create_test_user)
    inputs = _by_key(compute_condition(db, user.id, TODAY))
    assert inputs["load_ratio"]["available"] is False


# ── HRV trend (input 6) ─────────────────────────────────────────────────────

def _seed_hrv(db, user_id, *, long_value=60, short_value=54, source="whoop_screenshot",
              short_days=7, long_days=28):
    for offset in range(long_days):
        day = TODAY - timedelta(days=offset)
        value = short_value if offset < short_days else long_value
        _activity(db, user_id, day, source=source, hrv=value)


def test_hrv_trend_present_shifts_recovery_weight(db, create_test_user, monkeypatch):
    user = _user(create_test_user)
    _patch_load(monkeypatch, None)
    _seed_hrv(db, user.id)
    row = db.query(DailyActivity).filter(
        DailyActivity.user_id == user.id, DailyActivity.date == TODAY
    ).first()
    row.recovery_score = 80
    db.commit()

    result = compute_condition(db, user.id, TODAY)
    inputs = _by_key(result)
    # 7-day mean 54 vs 28-day mean 58.5 → ratio 0.923 → 100 − 300 × 0.077 ≈ 77
    assert inputs["hrv_trend"]["available"] is True
    assert inputs["hrv_trend"]["raw"] == 0.923
    assert inputs["hrv_trend"]["subscore"] == 77
    assert inputs["hrv_trend"]["source"] == "whoop"
    assert inputs["hrv_trend"]["weight"] == 0.10
    assert inputs["hrv_trend"]["label"] == "HRV Trend"
    assert inputs["recovery"]["weight"] == RECOVERY_WEIGHT_WITH_HRV
    # recovery 0.30 + cooldowns 0.25 + hrv 0.10 = 0.65 available
    assert inputs["recovery"]["effective_weight"] == round(0.30 / 0.65, 4)
    # effective_weight is rounded to 4 places per input, so the sum may land
    # a rounding unit shy of 1 — assert to 3 places.
    assert round(sum(i["effective_weight"] for i in result["inputs"]), 3) == 1.0
    # (80×0.30 + 100×0.25 + 77×0.10) / 0.65 ≈ 87
    assert result["score"] == 87


def test_hrv_trend_needs_four_recent_and_ten_total_days(db, create_test_user, monkeypatch):
    user = _user(create_test_user)
    _patch_load(monkeypatch, None)
    # Only 3 of the last 7 days have HRV (plus plenty older) → unavailable.
    for offset in list(range(3)) + list(range(7, 28)):
        _activity(db, user.id, TODAY - timedelta(days=offset), hrv=60)
    _activity(db, user.id, TODAY, source="apple_fitness", recovery_score=None)

    inputs = _by_key(compute_condition(db, user.id, TODAY))
    assert inputs["hrv_trend"]["available"] is False
    assert inputs["recovery"]["weight"] == 0.40   # no shift without HRV


def test_hrv_trend_needs_ten_days_in_28(db, create_test_user, monkeypatch):
    user = _user(create_test_user)
    _patch_load(monkeypatch, None)
    for offset in range(7):   # 7 recent days, nothing older → 7 < 10 total
        _activity(db, user.id, TODAY - timedelta(days=offset), hrv=60)
    inputs = _by_key(compute_condition(db, user.id, TODAY))
    assert inputs["hrv_trend"]["available"] is False


def test_hrv_badge_follows_row_source_and_whoop_wins(db, create_test_user, monkeypatch):
    user = _user(create_test_user)
    _patch_load(monkeypatch, None)
    _seed_hrv(db, user.id, source="apple_fitness", long_value=60, short_value=60)
    inputs = _by_key(compute_condition(db, user.id, TODAY))
    assert inputs["hrv_trend"]["available"] is True
    assert inputs["hrv_trend"]["subscore"] == 100
    assert inputs["hrv_trend"]["source"] == "apple_watch"

    # A WHOOP row on the latest day wins the day's value and the badge.
    _activity(db, user.id, TODAY, source="whoop_screenshot", hrv=30)
    inputs = _by_key(compute_condition(db, user.id, TODAY))
    assert inputs["hrv_trend"]["source"] == "whoop"
    assert inputs["hrv_trend"]["raw"] < 1.0


def test_all_six_inputs_renormalize_to_one(db, create_test_user, monkeypatch):
    user = _user(create_test_user)
    _patch_load(monkeypatch, 1.0)
    _seed_hrv(db, user.id, long_value=60, short_value=60)
    for offset in range(1, 8):
        row = db.query(DailyActivity).filter(
            DailyActivity.user_id == user.id, DailyActivity.date == TODAY - timedelta(days=offset)
        ).first()
        row.resting_heart_rate = 55
    today_row = db.query(DailyActivity).filter(
        DailyActivity.user_id == user.id, DailyActivity.date == TODAY
    ).first()
    today_row.recovery_score = 90
    today_row.sleep_hours = 7.5
    today_row.resting_heart_rate = 55
    db.commit()

    result = compute_condition(db, user.id, TODAY)
    inputs = _by_key(result)
    assert all(i["available"] for i in result["inputs"])
    assert round(sum(i["weight"] for i in result["inputs"]), 6) == 1.0
    # effective_weight is rounded to 4 places per input, so the sum may land
    # a rounding unit shy of 1 — assert to 3 places.
    assert round(sum(i["effective_weight"] for i in result["inputs"]), 3) == 1.0
    assert inputs["recovery"]["effective_weight"] == 0.30
    assert inputs["hrv_trend"]["effective_weight"] == 0.10
    assert inputs["load_ratio"]["effective_weight"] == 0.10
    # Every subscore is 100 except recovery (90) → 100 − 3 = 97
    assert result["score"] == 97
