"""
Shared schema bases.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator

from app.core.utils import ensure_utc


class UTCModel(BaseModel):
    """Naive DB datetimes serialize as UTC (``…Z``) instead of offset-less.

    SQLite and the Postgres ``timestamp without time zone`` columns both hand
    back naive instants that are UTC by convention; a browser would parse an
    offset-less ISO string as local time. Applies :func:`ensure_utc` to
    every datetime field before validation.
    """

    @field_validator("*", mode="before")
    @classmethod
    def _naive_datetimes_are_utc(cls, value: Any) -> Any:
        return ensure_utc(value) if isinstance(value, datetime) else value
