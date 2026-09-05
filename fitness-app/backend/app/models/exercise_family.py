"""
Exercise family model (ARISE v3 spec §4.2).

A family is the one canonicalization scheme for lifts: the prescription
engine anchors on it, gates spawn on it, load and the coach group by it.
Rows are seeded from ``app.services.exercise_family_defs.FAMILY_DEFS`` by the
``v3_exercise_families`` migration and kept in sync by
``exercise_family_service.ensure_families``.
"""
from sqlalchemy import Boolean, Column, Float, String
from sqlalchemy.orm import relationship

from app.core.database import Base


class ExerciseFamily(Base):
    """One movement family (e.g. ``back_squat``) spanning canonical + aliases."""
    __tablename__ = "exercise_families"

    id = Column(String, primary_key=True)  # slug, e.g. "back_squat"
    display_name = Column(String, nullable=False)
    primary_muscle = Column(String, nullable=True)
    is_big_three = Column(Boolean, nullable=False, default=False, server_default="false")
    # Key into api/analytics.STRENGTH_STANDARDS; NULL when no standard exists.
    standards_key = Column(String, nullable=True)
    # Default progression step in lb (5 barbell/machine/cable, 2.5 dumbbell).
    increment_lb = Column(Float, nullable=False, default=5.0, server_default="5.0")

    exercises = relationship("Exercise", back_populates="family")
