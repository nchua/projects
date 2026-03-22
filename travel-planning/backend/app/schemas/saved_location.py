"""Saved location Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CreateSavedLocationRequest(BaseModel):
    """Request body for POST /locations."""

    name: str = Field(max_length=100)
    address: str = Field(max_length=500)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    icon: str | None = Field(default=None, max_length=50)
    sort_order: int = 0


class UpdateSavedLocationRequest(BaseModel):
    """Request body for PUT /locations/{location_id}."""

    name: str | None = Field(default=None, max_length=100)
    address: str | None = Field(default=None, max_length=500)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    icon: str | None = Field(default=None, max_length=50)
    sort_order: int | None = None

    @model_validator(mode="after")
    def validate_address_group(self) -> "UpdateSavedLocationRequest":
        """If any of address/lat/lng is provided, all three must be provided."""
        fields = [self.address, self.latitude, self.longitude]
        provided = [f is not None for f in fields]
        if any(provided) and not all(provided):
            raise ValueError(
                "address, latitude, and longitude must all be provided together"
            )
        return self


class SavedLocationResponse(BaseModel):
    """Response body for saved location endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    address: str
    latitude: float
    longitude: float
    icon: str | None
    sort_order: int
    created_at: datetime
    updated_at: datetime
