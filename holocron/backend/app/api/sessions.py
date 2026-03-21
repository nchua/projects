"""Session API — review session management with pacing and interleaving."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.review import Review, Rating
from app.models.learning_unit import LearningUnit
from app.models.concept import Concept
from app.models.topic import Topic
from app.schemas.session import (
    SessionStartResponse,
    SessionCard,
    SessionSummaryResponse,
    TopicPerformance,
)
from app.services.session import (
    SessionMode,
    get_session_cards,
    SESSION_CARD_LIMITS,
)
from app.core.config import settings

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/start", response_model=SessionStartResponse)
def start_session(
    mode: SessionMode = Query(default=SessionMode.FULL),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionStartResponse:
    """Start a review session — returns ordered cards with pacing applied.

    Modes:
      - quick: ~5 min, 5-8 cards
      - full: ~10 min, 15-20 cards
      - deep: ~20 min, 25-30 cards

    Cards are ordered: warm-up → core → challenge → cool-down,
    interleaved by topic within each phase.
    """
    now = datetime.now(timezone.utc)

    scored_cards = get_session_cards(
        user_id=user.id,
        db=db,
        mode=mode,
        now=now,
    )

    # Count today's reviews for cap display
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    reviews_today = (
        db.query(Review)
        .filter(Review.user_id == user.id, Review.reviewed_at >= today_start)
        .count()
    )

    # Count total due (before session limits)
    total_due = (
        db.query(LearningUnit)
        .join(Concept)
        .join(Topic)
        .filter(
            Topic.user_id == user.id,
            LearningUnit.auto_accepted == True,  # noqa: E712
            LearningUnit.next_review_at.isnot(None),
            LearningUnit.next_review_at <= now.replace(tzinfo=None),
        )
        .count()
    )

    # Collect unique topics
    topics_today = list({c.topic_name for c in scored_cards})

    # Estimate session time (~30 sec per card)
    estimated_minutes = max(1, round(len(scored_cards) * 0.5))

    cards = [
        SessionCard(
            id=c.unit.id,
            concept_id=c.unit.concept_id,
            type=c.unit.type,
            front_content=c.unit.front_content,
            back_content=c.unit.back_content,
            topic_name=c.topic_name,
            source_name=c.source_name,
            phase=c.phase,
        )
        for c in scored_cards
    ]

    return SessionStartResponse(
        cards=cards,
        total_due=total_due,
        session_size=len(cards),
        estimated_minutes=estimated_minutes,
        topics=topics_today,
        reviews_today=reviews_today,
        daily_cap=settings.FSRS_DAILY_REVIEW_CAP,
        mode=mode,
    )


@router.get("/summary", response_model=SessionSummaryResponse)
def session_summary(
    since_minutes: int = Query(default=30, ge=1, le=1440),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionSummaryResponse:
    """Enhanced post-session summary with per-topic breakdowns.

    Includes strongest/weakest topic, per-topic stats, and mastery changes.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - __import__("datetime").timedelta(minutes=since_minutes)

    reviews = (
        db.query(Review)
        .filter(Review.user_id == user.id, Review.reviewed_at >= cutoff)
        .all()
    )

    if not reviews:
        return SessionSummaryResponse(
            total_reviewed=0,
            recalled=0,
            struggled=0,
            forgot=0,
            topic_performance=[],
        )

    # Overall stats
    recalled = sum(1 for r in reviews if r.rating in (Rating.GOT_IT, Rating.EASY))
    struggled = sum(1 for r in reviews if r.rating == Rating.STRUGGLED)
    forgot = sum(1 for r in reviews if r.rating == Rating.FORGOT)

    # Session duration
    times = sorted(r.reviewed_at for r in reviews)
    duration = int((times[-1] - times[0]).total_seconds()) if len(times) > 1 else 0

    # Per-topic breakdown
    topic_stats: dict[str, dict] = {}
    for review in reviews:
        unit = (
            db.query(LearningUnit)
            .filter(LearningUnit.id == review.learning_unit_id)
            .first()
        )
        if not unit:
            continue
        concept = db.query(Concept).filter(Concept.id == unit.concept_id).first()
        if not concept:
            continue
        topic = db.query(Topic).filter(Topic.id == concept.topic_id).first()
        if not topic:
            continue

        name = topic.name
        if name not in topic_stats:
            topic_stats[name] = {
                "total": 0,
                "recalled": 0,
                "struggled": 0,
                "forgot": 0,
            }
        topic_stats[name]["total"] += 1
        if review.rating in (Rating.GOT_IT, Rating.EASY):
            topic_stats[name]["recalled"] += 1
        elif review.rating == Rating.STRUGGLED:
            topic_stats[name]["struggled"] += 1
        else:
            topic_stats[name]["forgot"] += 1

    topic_performance = []
    for name, stats in topic_stats.items():
        accuracy = stats["recalled"] / stats["total"] if stats["total"] > 0 else 0.0
        topic_performance.append(TopicPerformance(
            topic_name=name,
            total=stats["total"],
            recalled=stats["recalled"],
            struggled=stats["struggled"],
            forgot=stats["forgot"],
            accuracy=round(accuracy, 2),
        ))

    # Sort by accuracy to find strongest/weakest
    topic_performance.sort(key=lambda t: t.accuracy, reverse=True)
    strongest = topic_performance[0].topic_name if topic_performance else None
    weakest = topic_performance[-1].topic_name if len(topic_performance) > 1 else None

    return SessionSummaryResponse(
        total_reviewed=len(reviews),
        recalled=recalled,
        struggled=struggled,
        forgot=forgot,
        session_duration_seconds=duration,
        strongest_topic=strongest,
        weakest_topic=weakest,
        topic_performance=topic_performance,
    )
