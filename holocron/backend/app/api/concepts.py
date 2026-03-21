from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.topic import Topic
from app.models.concept import Concept
from app.models.learning_unit import LearningUnit
from app.schemas.concept import ConceptCreate, ConceptUpdate, ConceptResponse

router = APIRouter(prefix="/concepts", tags=["concepts"])


def _enrich(concept: Concept, db: Session) -> ConceptResponse:
    """Add unit_count to concept response."""
    count = (
        db.query(func.count(LearningUnit.id))
        .filter(LearningUnit.concept_id == concept.id)
        .scalar()
    )
    return ConceptResponse(
        id=concept.id,
        topic_id=concept.topic_id,
        name=concept.name,
        description=concept.description,
        mastery_score=concept.mastery_score,
        tier=concept.tier,
        created_at=concept.created_at,
        unit_count=count,
    )


@router.get("", response_model=list[ConceptResponse])
def list_concepts(
    topic_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List concepts, optionally filtered by topic."""
    query = db.query(Concept).join(Topic).filter(Topic.user_id == user.id)
    if topic_id is not None:
        query = query.filter(Concept.topic_id == topic_id)
    concepts = query.all()
    return [_enrich(c, db) for c in concepts]


@router.post("", response_model=ConceptResponse, status_code=201)
def create_concept(
    req: ConceptCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new concept under a topic."""
    topic = (
        db.query(Topic)
        .filter(Topic.id == req.topic_id, Topic.user_id == user.id)
        .first()
    )
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    concept = Concept(**req.model_dump())
    db.add(concept)
    db.commit()
    db.refresh(concept)
    return _enrich(concept, db)


@router.get("/{concept_id}", response_model=ConceptResponse)
def get_concept(
    concept_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single concept."""
    concept = (
        db.query(Concept)
        .join(Topic)
        .filter(Concept.id == concept_id, Topic.user_id == user.id)
        .first()
    )
    if not concept:
        raise HTTPException(status_code=404, detail="Concept not found")
    return _enrich(concept, db)


@router.put("/{concept_id}", response_model=ConceptResponse)
def update_concept(
    concept_id: int,
    req: ConceptUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a concept."""
    concept = (
        db.query(Concept)
        .join(Topic)
        .filter(Concept.id == concept_id, Topic.user_id == user.id)
        .first()
    )
    if not concept:
        raise HTTPException(status_code=404, detail="Concept not found")

    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(concept, field, value)

    db.commit()
    db.refresh(concept)
    return _enrich(concept, db)


@router.delete("/{concept_id}", status_code=204)
def delete_concept(
    concept_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a concept and its learning units."""
    concept = (
        db.query(Concept)
        .join(Topic)
        .filter(Concept.id == concept_id, Topic.user_id == user.id)
        .first()
    )
    if not concept:
        raise HTTPException(status_code=404, detail="Concept not found")
    db.delete(concept)
    db.commit()
