"""Session service — interleaving, pacing, and anti-guilt card ordering.

Handles the logic for presenting cards in an optimal review session:
  - Interleaving: mix topics and card types for better retention
  - Pacing: warm-up → core → challenge → cool-down
  - Anti-guilt: spread overdue cards across days, enforce daily caps
"""

from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from enum import Enum
from collections import defaultdict

from sqlalchemy.orm import Session

from app.models.learning_unit import LearningUnit, UnitType
from app.models.concept import Concept
from app.models.topic import Topic
from app.models.review import Review, Rating
from app.core.config import settings
from app.core.fsrs import calculate_retrievability


class SessionMode(str, Enum):
    QUICK = "quick"      # ~5 min, 5-8 cards
    FULL = "full"        # ~10 min, 15-20 cards
    DEEP_DIVE = "deep"   # ~20 min, 25-30 cards


SESSION_CARD_LIMITS = {
    SessionMode.QUICK: 8,
    SessionMode.FULL: 20,
    SessionMode.DEEP_DIVE: 30,
}


@dataclass
class ScoredCard:
    """A card annotated with session metadata for ordering."""

    unit: LearningUnit
    topic_name: str
    source_name: str | None
    priority: float       # higher = more urgent
    phase: str            # "warmup", "core", "challenge", "cooldown"
    overdue_days: float   # how many days past due


def get_session_cards(
    user_id: int,
    db: Session,
    mode: SessionMode = SessionMode.FULL,
    now: datetime | None = None,
) -> list[ScoredCard]:
    """Get cards for a review session with interleaving and pacing.

    Combines three Phase 3 features:
    1. Anti-guilt: limits overdue cards, spreads them across days
    2. Pacing: orders cards warm-up → core → challenge → cool-down
    3. Interleaving: mixes topics within each phase

    Args:
        user_id: The authenticated user's ID.
        db: Database session.
        mode: Session size (quick/full/deep).
        now: Current time (defaults to utcnow).

    Returns:
        Ordered list of ScoredCards ready for review.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    card_limit = SESSION_CARD_LIMITS[mode]

    # Enforce daily review cap — subtract reviews already done today
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    reviews_today = (
        db.query(Review)
        .filter(Review.user_id == user_id, Review.reviewed_at >= today_start)
        .count()
    )
    remaining_cap = max(0, settings.FSRS_DAILY_REVIEW_CAP - reviews_today)
    card_limit = min(card_limit, remaining_cap)

    if card_limit == 0:
        return []

    # Fetch all due cards (generous limit, we'll trim after scoring)
    raw_cards = _fetch_due_cards(user_id, db, now, fetch_limit=card_limit * 3)

    if not raw_cards:
        return []

    # Score and assign phases
    scored = _score_cards(raw_cards, now)

    # Anti-guilt: spread overdue cards
    scored = _apply_overdue_spreading(scored, card_limit)

    # Assign pacing phases
    scored = _assign_phases(scored, card_limit)

    # Trim to session limit
    scored = scored[:card_limit]

    # Interleave within phases
    scored = _interleave(scored)

    return scored


def _fetch_due_cards(
    user_id: int,
    db: Session,
    now: datetime,
    fetch_limit: int = 90,
) -> list[tuple[LearningUnit, str, str | None]]:
    """Fetch due cards with topic and source names."""
    from app.models.source import Source

    now_naive = now.replace(tzinfo=None)

    rows = (
        db.query(LearningUnit, Topic.name, Source.name)
        .select_from(LearningUnit)
        .join(Concept, LearningUnit.concept_id == Concept.id)
        .join(Topic, Concept.topic_id == Topic.id)
        .outerjoin(Source, LearningUnit.source_id == Source.id)
        .filter(
            Topic.user_id == user_id,
            LearningUnit.auto_accepted == True,  # noqa: E712
            LearningUnit.next_review_at.isnot(None),
            LearningUnit.next_review_at <= now_naive,
        )
        .order_by(LearningUnit.next_review_at.asc())
        .limit(fetch_limit)
        .all()
    )

    return [(unit, topic_name, source_name) for unit, topic_name, source_name in rows]


def _score_cards(
    raw_cards: list[tuple[LearningUnit, str, str | None]],
    now: datetime,
) -> list[ScoredCard]:
    """Score each card by priority (higher = review sooner)."""
    scored = []
    for unit, topic_name, source_name in raw_cards:
        next_review = unit.next_review_at
        if next_review is not None:
            if next_review.tzinfo is None:
                next_review = next_review.replace(tzinfo=timezone.utc)
            overdue_days = max(0.0, (now - next_review).total_seconds() / 86400)
        else:
            overdue_days = 0.0

        # Priority: combine overdue-ness with retrievability decay
        if unit.stability > 0 and unit.last_reviewed_at is not None:
            last = unit.last_reviewed_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            elapsed = (now - last).total_seconds() / 86400
            retrievability = calculate_retrievability(unit.stability, elapsed)
        else:
            retrievability = 1.0 if unit.review_count > 0 else 0.5

        # Priority formula: overdue cards with low retrievability are most urgent
        priority = overdue_days * 2 + (1 - retrievability) * 3

        # New cards (never reviewed) get moderate priority
        if unit.review_count == 0:
            priority = 1.5

        scored.append(ScoredCard(
            unit=unit,
            topic_name=topic_name,
            source_name=source_name,
            priority=priority,
            phase="core",  # default, reassigned later
            overdue_days=overdue_days,
        ))

    scored.sort(key=lambda c: c.priority, reverse=True)
    return scored


def _apply_overdue_spreading(
    scored: list[ScoredCard],
    card_limit: int,
) -> list[ScoredCard]:
    """Anti-guilt: when many cards are overdue, only take a portion today.

    Instead of showing 100 overdue cards, show ~card_limit with a mix of
    heavily overdue and moderately overdue. Heavily overdue cards (>7 days)
    are capped at 40% of the session to avoid overwhelming the user.
    """
    heavily_overdue = [c for c in scored if c.overdue_days > 7]
    rest = [c for c in scored if c.overdue_days <= 7]

    # Cap heavily overdue at 40% of session
    max_heavy = int(card_limit * 0.4)
    if len(heavily_overdue) > max_heavy:
        heavily_overdue = heavily_overdue[:max_heavy]

    # Recombine and re-sort
    combined = heavily_overdue + rest
    combined.sort(key=lambda c: c.priority, reverse=True)
    return combined


def _assign_phases(
    scored: list[ScoredCard],
    card_limit: int,
) -> list[ScoredCard]:
    """Assign pacing phases: warm-up → core → challenge → cool-down.

    Distribution:
      - Warm-up (15%): easiest due cards (high retrievability, reviewed before)
      - Core (55%): standard due cards
      - Challenge (20%): new cards or cards that were previously forgotten
      - Cool-down (10%): easy familiar cards
    """
    n = min(len(scored), card_limit)
    if n == 0:
        return scored

    warmup_n = max(1, int(n * 0.15))
    cooldown_n = max(1, int(n * 0.10))
    challenge_n = max(1, int(n * 0.20))
    core_n = n - warmup_n - cooldown_n - challenge_n

    # Separate new cards (challenge candidates) from reviewed cards
    new_cards = [c for c in scored if c.unit.review_count == 0]
    lapsed_cards = [c for c in scored if c.unit.review_count > 0 and c.unit.lapse_count > 0]
    regular_cards = [
        c for c in scored
        if c.unit.review_count > 0 and c.unit.lapse_count == 0
    ]

    # Sort regular by priority ascending (easiest first for warm-up picks)
    regular_by_ease = sorted(regular_cards, key=lambda c: c.priority)

    result = []

    # Warm-up: easiest regular cards
    warmup = regular_by_ease[:warmup_n]
    for c in warmup:
        c.phase = "warmup"
    result.extend(warmup)
    remaining_regular = [c for c in regular_by_ease if c not in warmup]

    # Cool-down: next easiest (set aside, added at end)
    cooldown = remaining_regular[:cooldown_n]
    for c in cooldown:
        c.phase = "cooldown"
    remaining_regular = [c for c in remaining_regular if c not in cooldown]

    # Challenge: new cards + lapsed cards
    challenge_pool = new_cards + lapsed_cards
    challenge_pool.sort(key=lambda c: c.priority, reverse=True)
    challenge = challenge_pool[:challenge_n]
    for c in challenge:
        c.phase = "challenge"
    leftover_challenge = challenge_pool[challenge_n:]

    # Core: everything else
    core_pool = remaining_regular + leftover_challenge
    core_pool.sort(key=lambda c: c.priority, reverse=True)
    core = core_pool[:core_n]
    for c in core:
        c.phase = "core"

    # Assemble in pacing order: warmup → core → challenge → cooldown
    result = warmup + core + challenge + cooldown
    return result


def _interleave(scored: list[ScoredCard]) -> list[ScoredCard]:
    """Interleave cards by topic within each pacing phase.

    Within each phase, cards are reordered so consecutive cards come from
    different topics as much as possible. This leverages the interleaving
    effect for better long-term retention.
    """
    # Group by phase, preserving phase order
    phase_order = ["warmup", "core", "challenge", "cooldown"]
    phases: dict[str, list[ScoredCard]] = defaultdict(list)
    for card in scored:
        phases[card.phase].append(card)

    result = []
    for phase in phase_order:
        cards = phases.get(phase, [])
        if not cards:
            continue
        result.extend(_interleave_by_topic(cards))

    return result


def _interleave_by_topic(cards: list[ScoredCard]) -> list[ScoredCard]:
    """Round-robin interleave cards by topic name.

    Takes [A, A, A, B, B, C] and produces [A, B, C, A, B, A].
    """
    if len(cards) <= 1:
        return cards

    # Group by topic
    by_topic: dict[str, list[ScoredCard]] = defaultdict(list)
    for card in cards:
        by_topic[card.topic_name].append(card)

    # Sort topic groups by size descending (largest first for even distribution)
    topic_queues = sorted(by_topic.values(), key=len, reverse=True)

    result = []
    while any(topic_queues):
        next_round = []
        for queue in topic_queues:
            if queue:
                result.append(queue.pop(0))
            if queue:
                next_round.append(queue)
        topic_queues = sorted(next_round, key=len, reverse=True)

    return result
