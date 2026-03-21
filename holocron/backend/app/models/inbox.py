from datetime import datetime, timezone

from sqlalchemy import Float, DateTime, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.core.database import Base


class InboxStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class InboxItem(Base):
    __tablename__ = "inbox_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    learning_unit_id: Mapped[int] = mapped_column(
        ForeignKey("learning_units.id"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    confidence_score: Mapped[float] = mapped_column(Float)
    status: Mapped[InboxStatus] = mapped_column(
        Enum(InboxStatus, values_callable=lambda x: [e.value for e in x]), default=InboxStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    learning_unit: Mapped["LearningUnit"] = relationship()  # noqa: F821
