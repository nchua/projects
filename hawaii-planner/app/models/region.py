"""Seeded reference tables: Oahu planning regions and the drive-time matrix."""
from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, String

from app.core.database import Base


class Region(Base):
    __tablename__ = "regions"

    id = Column(String, primary_key=True)  # slug: WAI, HNL, PRL, ...
    name = Column(String, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    # Position in the canonical clockwise island loop (WAI=0 ... KOOL=8);
    # used to order bulk-added stops into a drive-sensible sequence.
    tour_order = Column(Integer, nullable=False, default=0)


class DriveTime(Base):
    """Symmetric upper-triangle matrix (region_a <= region_b), typical midday
    minutes. `flags` is a CSV of display-only caution tokens (H1_AM, H1_PM,
    NS_WKND, HANAUMA_AM_WKND) — never added to `minutes`; if flags ever feed
    the arithmetic the matrix must become directional first."""

    __tablename__ = "drive_times"
    __table_args__ = (CheckConstraint("region_a <= region_b", name="ck_drive_pair_ordered"),)

    region_a = Column(String, ForeignKey("regions.id"), primary_key=True)
    region_b = Column(String, ForeignKey("regions.id"), primary_key=True)
    minutes = Column(Integer, nullable=False)
    flags = Column(String, nullable=False, default="")
