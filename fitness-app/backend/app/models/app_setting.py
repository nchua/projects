"""
Console-editable settings (console v2 spec §6.5).

One row per key the owner has overridden from the console; a missing row
means the env / code value from ``Settings`` applies. ``settings_service.get``
is the only reader (row → env → code) and ``PATCH /admin/settings/{key}``
the only writer; a reset deletes the row. Keys are the
``SETTINGS_REGISTRY`` keys, never free-form.
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, String

from app.core.database import Base


class AppSetting(Base):
    """A console override of one registry key."""

    __tablename__ = "app_settings"

    key = Column(String, primary_key=True)
    value = Column(JSON, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_by = Column(String, nullable=True)  # admin user id; no FK (the trail outlives the account)
