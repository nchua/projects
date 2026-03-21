from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.topic import Topic
from app.models.concept import Concept
from app.schemas.topic import TopicCreate, TopicUpdate, TopicResponse

router = APIRouter(prefix="/topics", tags=["topics"])


def _enrich(topic: Topic, db: Session) -> TopicResponse:
    """Add computed fields (concept_count, mastery_pct) to topic response."""
    stats = (
        db.query(
            func.count(Concept.id),
            func.coalesce(func.avg(Concept.mastery_score), 0),
        )
        .filter(Concept.topic_id == topic.id)
        .first()
    )
    return TopicResponse(
        id=topic.id,
        name=topic.name,
        description=topic.description,
        target_retention=topic.target_retention,
        created_at=topic.created_at,
        concept_count=stats[0],
        mastery_pct=round(stats[1] * 100, 1),
    )


@router.get("", response_model=list[TopicResponse])
def list_topics(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all topics for the current user."""
    topics = db.query(Topic).filter(Topic.user_id == user.id).all()
    return [_enrich(t, db) for t in topics]


@router.post("", response_model=TopicResponse, status_code=201)
def create_topic(
    req: TopicCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new topic."""
    topic = Topic(user_id=user.id, **req.model_dump())
    db.add(topic)
    db.commit()
    db.refresh(topic)
    return _enrich(topic, db)


@router.get("/{topic_id}", response_model=TopicResponse)
def get_topic(
    topic_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single topic."""
    topic = (
        db.query(Topic).filter(Topic.id == topic_id, Topic.user_id == user.id).first()
    )
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    return _enrich(topic, db)


@router.put("/{topic_id}", response_model=TopicResponse)
def update_topic(
    topic_id: int,
    req: TopicUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a topic."""
    topic = (
        db.query(Topic).filter(Topic.id == topic_id, Topic.user_id == user.id).first()
    )
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(topic, field, value)

    db.commit()
    db.refresh(topic)
    return _enrich(topic, db)


@router.delete("/{topic_id}", status_code=204)
def delete_topic(
    topic_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a topic and its concepts/cards."""
    topic = (
        db.query(Topic).filter(Topic.id == topic_id, Topic.user_id == user.id).first()
    )
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    db.delete(topic)
    db.commit()
