from datetime import datetime, timezone

from sqlalchemy import Integer, DateTime, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.core.database import Base


class Rating(str, enum.Enum):
    FORGOT = "forgot"
    STRUGGLED = "struggled"
    GOT_IT = "got_it"
    EASY = "easy"


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    learning_unit_id: Mapped[int] = mapped_column(
        ForeignKey("learning_units.id"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    rating: Mapped[Rating] = mapped_column(Enum(Rating, values_callable=lambda x: [e.value for e in x]))
    time_to_reveal_ms: Mapped[int | None] = mapped_column(Integer)
    time_reading_ms: Mapped[int | None] = mapped_column(Integer)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    learning_unit: Mapped["LearningUnit"] = relationship(back_populates="reviews")  # noqa: F821
