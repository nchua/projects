"""Trip-day and schedule-item request schemas."""
from datetime import date as date_type
from datetime import time as time_type

from pydantic import BaseModel, Field, model_validator


class DayCreate(BaseModel):
    date: date_type | None = None
    label: str | None = Field(default=None, max_length=80)


class DayPatch(BaseModel):
    date: date_type | None = None
    label: str | None = Field(default=None, max_length=80)
    start_time: time_type | None = None
    end_time: time_type | None = None
    notes: str | None = None
    sort_order: int | None = None


class ItemCreate(BaseModel):
    idea_id: str | None = None
    free_text_title: str | None = Field(default=None, min_length=1, max_length=120)
    free_text_region_id: str | None = None
    position: int | None = Field(default=None, ge=0)
    duration_override_min: int | None = Field(default=None, ge=5, le=720)
    fixed_start_time: time_type | None = None
    drive_override_min: int | None = Field(default=None, ge=0, le=240)
    notes: str | None = None

    @model_validator(mode="after")
    def _idea_xor_free_text(self) -> "ItemCreate":
        if (self.idea_id is None) == (self.free_text_title is None):
            raise ValueError("Provide exactly one of idea_id or free_text_title")
        return self


class ItemPatch(BaseModel):
    """Partial update. Nullable overrides (fixed_start_time etc.) are cleared by
    explicitly sending null — the API distinguishes absent from null via
    model_fields_set."""

    trip_day_id: str | None = None  # move to another day (appended at the end)
    free_text_title: str | None = Field(default=None, min_length=1, max_length=120)
    free_text_region_id: str | None = None
    duration_override_min: int | None = Field(default=None, ge=5, le=720)
    fixed_start_time: time_type | None = None
    drive_override_min: int | None = Field(default=None, ge=0, le=240)
    notes: str | None = None


class OrderIn(BaseModel):
    item_ids: list[str] = Field(min_length=0)


class BulkAddIn(BaseModel):
    idea_ids: list[str] = Field(min_length=1)
