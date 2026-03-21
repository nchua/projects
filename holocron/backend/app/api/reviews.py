from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.fsrs import schedule_review
from app.models.user import User
from app.models.topic import Topic
from app.models.concept import Concept, ConceptTier
from app.models.learning_unit import LearningUnit
from app.models.review import Review, Rating
from app.schemas.review import ReviewCreate, ReviewResponse, SessionSummary

router = APIRouter(prefix="/reviews", tags=["reviews"])

# Mastery tier thresholds
TIER_THRESHOLDS = {
    0.0: ConceptTier.NEW,
    0.3: ConceptTier.LEARNING,
    0.6: ConceptTier.REVIEWING,
    0.85: ConceptTier.MASTERED,
}


def _update_concept_mastery(concept_id: int, db: Session) -> None:
    """Recalculate concept mastery from its learning units' retrievabilities."""
    units = db.query(LearningUnit).filter(LearningUnit.concept_id == concept_id).all()
    if not units:
        return

    avg_retrievability = sum(u.retrievability for u in units) / len(units)
    concept = db.query(Concept).filter(Concept.id == concept_id).first()
    if not concept:
        return

    concept.mastery_score = round(avg_retrievability, 4)

    # Update tier
    tier = ConceptTier.NEW
    for threshold, t in TIER_THRESHOLDS.items():
        if concept.mastery_score >= threshold:
            tier = t
    concept.tier = tier


@router.post("", response_model=ReviewResponse, status_code=201)
def submit_review(
    req: ReviewCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit a review rating for a learning unit.

    Triggers FSRS rescheduling and updates concept mastery.
    """
    # Verify unit belongs to user
    unit = (
        db.query(LearningUnit)
        .join(Concept)
        .join(Topic)
        .filter(LearningUnit.id == req.learning_unit_id, Topic.user_id == user.id)
        .first()
    )
    if not unit:
        raise HTTPException(status_code=404, detail="Learning unit not found")

    # Get topic retention target
    topic = db.query(Topic).join(Concept).filter(Concept.id == unit.concept_id).first()
    target_retention = topic.target_retention if topic else 0.9

    now = datetime.now(timezone.utc)

    # Run FSRS scheduler
    result = schedule_review(
        rating=req.rating,
        current_difficulty=unit.difficulty,
        current_stability=unit.stability,
        last_reviewed_at=unit.last_reviewed_at,
        review_count=unit.review_count,
        ai_generated=unit.ai_generated,
        target_retention=target_retention,
        now=now,
    )

    # Save review record
    review = Review(
        learning_unit_id=unit.id,
        user_id=user.id,
        rating=req.rating,
        time_to_reveal_ms=req.time_to_reveal_ms,
        time_reading_ms=req.time_reading_ms,
        reviewed_at=now,
    )
    db.add(review)

    # Update learning unit FSRS state
    unit.difficulty = result.difficulty
    unit.stability = result.stability
    unit.retrievability = result.retrievability
    unit.last_reviewed_at = now
    unit.next_review_at = result.next_review_at
    unit.review_count += 1
    if req.rating == Rating.FORGOT:
        unit.lapse_count += 1

    # Update concept mastery
    _update_concept_mastery(unit.concept_id, db)

    db.commit()
    db.refresh(review)

    return ReviewResponse(
        id=review.id,
        learning_unit_id=review.learning_unit_id,
        rating=review.rating,
        time_to_reveal_ms=review.time_to_reveal_ms,
        time_reading_ms=review.time_reading_ms,
        reviewed_at=review.reviewed_at,
        next_review_at=unit.next_review_at,
    )


@router.get("/history", response_model=list[ReviewResponse])
def review_history(
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get recent review history."""
    reviews = (
        db.query(Review)
        .filter(Review.user_id == user.id)
        .order_by(Review.reviewed_at.desc())
        .limit(limit)
        .all()
    )
    results = []
    for r in reviews:
        unit = (
            db.query(LearningUnit).filter(LearningUnit.id == r.learning_unit_id).first()
        )
        results.append(
            ReviewResponse(
                id=r.id,
                learning_unit_id=r.learning_unit_id,
                rating=r.rating,
                time_to_reveal_ms=r.time_to_reveal_ms,
                time_reading_ms=r.time_reading_ms,
                reviewed_at=r.reviewed_at,
                next_review_at=unit.next_review_at if unit else None,
            )
        )
    return results


@router.get("/summary", response_model=SessionSummary)
def session_summary(
    since_minutes: int = 30,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get summary stats for the current review session."""
    cutoff = datetime.now(timezone.utc) - __import__("datetime").timedelta(
        minutes=since_minutes
    )

    reviews = (
        db.query(Review)
        .filter(Review.user_id == user.id, Review.reviewed_at >= cutoff)
        .all()
    )

    if not reviews:
        return SessionSummary(total_reviewed=0, recalled=0, struggled=0, forgot=0)

    recalled = sum(1 for r in reviews if r.rating in (Rating.GOT_IT, Rating.EASY))
    struggled = sum(1 for r in reviews if r.rating == Rating.STRUGGLED)
    forgot = sum(1 for r in reviews if r.rating == Rating.FORGOT)

    # Calculate session duration from first to last review
    times = sorted(r.reviewed_at for r in reviews)
    duration = int((times[-1] - times[0]).total_seconds()) if len(times) > 1 else 0

    return SessionSummary(
        total_reviewed=len(reviews),
        recalled=recalled,
        struggled=struggled,
        forgot=forgot,
        session_duration_seconds=duration,
    )
