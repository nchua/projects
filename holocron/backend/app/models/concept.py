from datetime import datetime, timezone

from sqlalchemy import String, Float, DateTime, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.core.database import Base


class ConceptTier(str, enum.Enum):
    NEW = "new"
    LEARNING = "learning"
    REVIEWING = "reviewing"
    MASTERED = "mastered"


class EdgeType(str, enum.Enum):
    PREREQUISITE = "prerequisite"
    SUPPORTS = "supports"
    RELATES_TO = "relates_to"
    PART_OF = "part_of"


class Concept(Base):
    __tablename__ = "concepts"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(String(2000))
    mastery_score: Mapped[float] = mapped_column(Float, default=0.0)
    tier: Mapped[ConceptTier] = mapped_column(
        Enum(ConceptTier, values_callable=lambda x: [e.value for e in x]),
        default=ConceptTier.NEW,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    topic: Mapped["Topic"] = relationship(back_populates="concepts")  # noqa: F821
    learning_units: Mapped[list["LearningUnit"]] = relationship(  # noqa: F821
        back_populates="concept"
    )


class ConceptRelationship(Base):
    __tablename__ = "concept_relationships"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_concept_id: Mapped[int] = mapped_column(
        ForeignKey("concepts.id"), index=True
    )
    target_concept_id: Mapped[int] = mapped_column(
        ForeignKey("concepts.id"), index=True
    )
    edge_type: Mapped[EdgeType] = mapped_column(
        Enum(EdgeType, values_callable=lambda x: [e.value for e in x])
    )

    source: Mapped["Concept"] = relationship(foreign_keys=[source_concept_id])
    target: Mapped["Concept"] = relationship(foreign_keys=[target_concept_id])
