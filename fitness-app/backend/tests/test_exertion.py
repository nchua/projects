"""
Tests for the HR-zone exertion score (app.core.exertion).

Apple-Watch cardio sessions carry no WHOOP strain, so `compute_exertion_score`
derives a 0-21 strain-like value from the time-in-zone breakdown. These tests
pin the contract: None when there's no usable data, monotonic in both intensity
and duration, and clamped to [0, 21].
"""
from app.core.exertion import MAX_EXERTION, compute_exertion_score


def test_none_and_empty_return_none():
    assert compute_exertion_score(None) is None
    assert compute_exertion_score({}) is None


def test_non_positive_seconds_ignored_returns_none():
    # Zero/negative seconds carry no load -> no score.
    assert compute_exertion_score({"z3": 0}) is None
    assert compute_exertion_score({"z2": -100}) is None


def test_higher_zone_scores_higher_for_same_duration():
    easy = compute_exertion_score({"z2": 3600})
    hard = compute_exertion_score({"z4": 3600})
    assert easy is not None and hard is not None
    assert hard > easy


def test_longer_duration_scores_higher_for_same_zone():
    short = compute_exertion_score({"z3": 1800})
    long = compute_exertion_score({"z3": 3600})
    assert long > short


def test_capped_at_max():
    # Two hours pinned in z5 would exceed the raw scale; must clamp to 21.
    assert compute_exertion_score({"z5": 7200}) == MAX_EXERTION


def test_one_hour_z5_is_max():
    assert compute_exertion_score({"z5": 3600}) == MAX_EXERTION


def test_unknown_zone_keys_contribute_no_score():
    # An unrecognized zone name adds duration but no weighted load -> no signal,
    # so the score rounds to zero and is reported as None (clients hide it).
    assert compute_exertion_score({"bogus": 3600}) is None


def test_mixed_zones_between_bounds():
    score = compute_exertion_score({"z1": 600, "z2": 1200, "z3": 1200})
    assert 0.0 < score < MAX_EXERTION
