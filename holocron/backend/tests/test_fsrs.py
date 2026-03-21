"""Tests for FSRS scheduler engine."""

from datetime import datetime, timedelta, timezone

from app.core.fsrs import (
    calculate_retrievability,
    initial_difficulty,
    initial_stability,
    optimal_interval,
    schedule_review,
)
from app.models.review import Rating


def test_retrievability_at_zero():
    """At t=0, retrievability should be 1.0."""
    r = calculate_retrievability(stability=5.0, elapsed_days=0.0)
    assert r == 1.0


def test_retrievability_decays():
    """Retrievability should decrease over time."""
    r1 = calculate_retrievability(stability=5.0, elapsed_days=1.0)
    r2 = calculate_retrievability(stability=5.0, elapsed_days=5.0)
    r3 = calculate_retrievability(stability=5.0, elapsed_days=30.0)
    assert 1.0 > r1 > r2 > r3 > 0.0


def test_retrievability_higher_stability():
    """Higher stability means slower decay."""
    r_low = calculate_retrievability(stability=2.0, elapsed_days=5.0)
    r_high = calculate_retrievability(stability=10.0, elapsed_days=5.0)
    assert r_high > r_low


def test_initial_difficulty_range():
    """Initial difficulty for all grades should be in [0.1, 0.9]."""
    for grade in [1, 2, 3, 4]:
        d = initial_difficulty(grade)
        assert 0.1 <= d <= 0.9


def test_initial_stability_ordering():
    """Higher grades should give higher initial stability."""
    s1 = initial_stability(1)
    s2 = initial_stability(2)
    s3 = initial_stability(3)
    s4 = initial_stability(4)
    assert s1 < s2 < s3 < s4


def test_optimal_interval_at_90_retention():
    """At 90% retention, interval ≈ stability (t = 9*S*(R^-1 - 1))."""
    interval = optimal_interval(stability=5.0, target_retention=0.9)
    assert abs(interval - 5.0) < 0.1  # interval ≈ S at 90% retention


def test_schedule_first_review_got_it():
    """First review with 'got_it' should set reasonable parameters."""
    result = schedule_review(
        rating=Rating.GOT_IT,
        current_difficulty=0.3,
        current_stability=0.0,
        last_reviewed_at=None,
        review_count=0,
    )
    assert result.difficulty > 0
    assert result.stability > 0
    assert result.next_review_at > datetime.now(timezone.utc)
    assert result.interval_days > 0


def test_schedule_first_review_forgot():
    """First review with 'forgot' should give short interval."""
    result = schedule_review(
        rating=Rating.FORGOT,
        current_difficulty=0.3,
        current_stability=0.0,
        last_reviewed_at=None,
        review_count=0,
    )
    assert result.stability < 1.0  # short stability
    assert result.interval_days < 1.0  # review again soon


def test_schedule_easy_longer_than_got_it():
    """'Easy' should give a longer interval than 'got_it' on first review."""
    got_it = schedule_review(
        rating=Rating.GOT_IT,
        current_difficulty=0.3,
        current_stability=0.0,
        last_reviewed_at=None,
        review_count=0,
    )
    easy = schedule_review(
        rating=Rating.EASY,
        current_difficulty=0.3,
        current_stability=0.0,
        last_reviewed_at=None,
        review_count=0,
    )
    assert easy.interval_days > got_it.interval_days


def test_schedule_subsequent_review_grows():
    """Successive 'got_it' reviews should increase intervals."""
    now = datetime.now(timezone.utc)

    # First review
    r1 = schedule_review(
        rating=Rating.GOT_IT,
        current_difficulty=0.3,
        current_stability=0.0,
        last_reviewed_at=None,
        review_count=0,
        now=now,
    )

    # Second review (after the interval)
    later = now + timedelta(days=r1.interval_days)
    r2 = schedule_review(
        rating=Rating.GOT_IT,
        current_difficulty=r1.difficulty,
        current_stability=r1.stability,
        last_reviewed_at=now,
        review_count=1,
        now=later,
    )

    assert r2.interval_days > r1.interval_days


def test_ai_generated_shorter_initial():
    """AI-generated cards should have shorter initial stability."""
    human = schedule_review(
        rating=Rating.GOT_IT,
        current_difficulty=0.3,
        current_stability=0.0,
        last_reviewed_at=None,
        review_count=0,
        ai_generated=False,
    )
    ai = schedule_review(
        rating=Rating.GOT_IT,
        current_difficulty=0.3,
        current_stability=0.0,
        last_reviewed_at=None,
        review_count=0,
        ai_generated=True,
    )
    assert ai.stability < human.stability
    assert ai.interval_days < human.interval_days


def test_lapse_reduces_stability():
    """Forgetting a previously-known card should reduce stability."""
    now = datetime.now(timezone.utc)

    # First good review
    r1 = schedule_review(
        rating=Rating.GOT_IT,
        current_difficulty=0.3,
        current_stability=0.0,
        last_reviewed_at=None,
        review_count=0,
        now=now,
    )

    # Then forget it
    later = now + timedelta(days=r1.interval_days)
    r2 = schedule_review(
        rating=Rating.FORGOT,
        current_difficulty=r1.difficulty,
        current_stability=r1.stability,
        last_reviewed_at=now,
        review_count=1,
        now=later,
    )

    assert r2.stability < r1.stability
    assert r2.interval_days < r1.interval_days
