"""Trip ETA snapshot model — one row per traffic check."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import ForeignKey
from sqlalchemy.sql import func

from app.core.database import Base
from app.models.enums import CongestionLevel


class TripEtaSnapshot(Base):
    __tablename__ = "trip_eta_snapshots"
    __table_args__ = (
        Index(
            "ix_trip_eta_snapshots_trip_checked",
            "trip_id",
            "checked_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    trip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trips.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_in_traffic_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    traffic_model: Mapped[str] = mapped_column(
        String(50), nullable=False, default="best_guess"
    )
    congestion_level: Mapped[CongestionLevel] = mapped_column(
        Enum(
            CongestionLevel,
            name="congestionlevel",
            create_constraint=True,
        ),
        nullable=False,
        default=CongestionLevel.unknown,
    )
    distance_meters: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    raw_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    trip = relationship("Trip", back_populates="eta_snapshots")
