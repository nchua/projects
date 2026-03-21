from datetime import datetime, timezone

from sqlalchemy import Float, Boolean, DateTime, ForeignKey, Enum, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.core.database import Base


class UnitType(str, enum.Enum):
    CONCEPT = "concept"
    CLOZE = "cloze"
    EXPLANATION = "explanation"
    APPLICATION = "application"
    CONNECTION = "connection"
    GENERATIVE = "generative"


class LearningUnit(Base):
    __tablename__ = "learning_units"

    id: Mapped[int] = mapped_column(primary_key=True)
    concept_id: Mapped[int] = mapped_column(ForeignKey("concepts.id"), index=True)
    type: Mapped[UnitType] = mapped_column(
        Enum(UnitType, values_callable=lambda x: [e.value for e in x])
    )
    front_content: Mapped[str] = mapped_column(Text)
    back_content: Mapped[str] = mapped_column(Text)

    # FSRS parameters
    difficulty: Mapped[float] = mapped_column(Float, default=0.3)
    stability: Mapped[float] = mapped_column(Float, default=0.0)
    retrievability: Mapped[float] = mapped_column(Float, default=1.0)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_review_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    review_count: Mapped[int] = mapped_column(default=0)
    lapse_count: Mapped[int] = mapped_column(default=0)

    # Provenance
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"))
    auto_accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    concept: Mapped["Concept"] = relationship(back_populates="learning_units")  # noqa: F821
    source: Mapped["Source | None"] = relationship()  # noqa: F821
    reviews: Mapped[list["Review"]] = relationship(back_populates="learning_unit")  # noqa: F821
