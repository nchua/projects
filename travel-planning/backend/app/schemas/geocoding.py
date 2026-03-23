"""Geocoding request/response schemas."""

from pydantic import BaseModel, Field


class GeocodeRequest(BaseModel):
    """Request to geocode an address to coordinates."""

    address: str = Field(
        min_length=2,
        max_length=500,
        description="Address or place name to geocode",
    )


class GeocodeResponse(BaseModel):
    """Geocoding result with coordinates."""

    lat: float = Field(description="Latitude")
    lng: float = Field(description="Longitude")
    address: str = Field(description="Original query address")
