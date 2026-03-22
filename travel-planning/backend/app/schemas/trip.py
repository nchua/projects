"""Trip-related Pydantic schemas."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

VALID_TRAVEL_MODES = {"driving", "transit", "walking", "cycling"}
VALID_CLIENT_STATUSES = {"cancelled", "departed"}


class CreateTripRequest(BaseModel):
    """Request body for creating a new trip."""

    name: str = Field(max_length=255)
    origin_address: str | None = Field(default=None, max_length=500)
    origin_lat: float | None = None
    origin_lng: float | None = None
    origin_location_id: UUID | None = None
    origin_is_current_location: bool = False
    dest_address: str = Field(max_length=500)
    dest_lat: float = Field(ge=-90, le=90)
    dest_lng: float = Field(ge=-180, le=180)
    dest_location_id: UUID | None = None
    arrival_time: datetime
    travel_mode: str | None = None
    buffer_minutes: int | None = Field(default=None, ge=0, le=120)
    is_recurring: bool = False
    recurrence_rule: dict[str, Any] | None = None
    calendar_event_id: str | None = Field(default=None, max_length=500)

    @field_validator("arrival_time")
    @classmethod
    def validate_future(cls, v: datetime) -> datetime:
        """Arrival time must be in the future."""
        now = datetime.now(timezone.utc)
        compare_v = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        if compare_v <= now:
            raise ValueError("Arrival time must be in the future")
        return v

    @field_validator("travel_mode")
    @classmethod
    def validate_travel_mode(cls, v: str | None) -> str | None:
        """Travel mode must be a valid option if provided."""
        if v is not None and v not in VALID_TRAVEL_MODES:
            raise ValueError(
                f"travel_mode must be one of {sorted(VALID_TRAVEL_MODES)}"
            )
        return v

    @field_validator("origin_lat")
    @classmethod
    def validate_origin_lat_range(cls, v: float | None) -> float | None:
        """Origin latitude must be in valid range."""
        if v is not None and not (-90 <= v <= 90):
            raise ValueError("origin_lat must be between -90 and 90")
        return v

    @field_validator("origin_lng")
    @classmethod
    def validate_origin_lng_range(cls, v: float | None) -> float | None:
        """Origin longitude must be in valid range."""
        if v is not None and not (-180 <= v <= 180):
            raise ValueError("origin_lng must be between -180 and 180")
        return v

    @model_validator(mode="after")
    def validate_origin(self) -> "CreateTripRequest":
        """If not using current location, origin address/lat/lng are required."""
        if not self.origin_is_current_location:
            missing = []
            if self.origin_address is None:
                missing.append("origin_address")
            if self.origin_lat is None:
                missing.append("origin_lat")
            if self.origin_lng is None:
                missing.append("origin_lng")
            if missing:
                raise ValueError(
                    f"When origin_is_current_location is false, "
                    f"{', '.join(missing)} must be provided"
                )
        return self

    @model_validator(mode="after")
    def validate_recurrence(self) -> "CreateTripRequest":
        """Recurrence rule is required if trip is recurring."""
        if self.is_recurring and not self.recurrence_rule:
            raise ValueError(
                "recurrence_rule is required when is_recurring is true"
            )
        return self


class UpdateTripRequest(BaseModel):
    """Request body for updating a trip. All fields optional."""

    name: str | None = Field(default=None, max_length=255)
    origin_address: str | None = Field(default=None, max_length=500)
    origin_lat: float | None = None
    origin_lng: float | None = None
    origin_location_id: UUID | None = None
    origin_is_current_location: bool | None = None
    dest_address: str | None = Field(default=None, max_length=500)
    dest_lat: float | None = None
    dest_lng: float | None = None
    dest_location_id: UUID | None = None
    arrival_time: datetime | None = None
    travel_mode: str | None = None
    buffer_minutes: int | None = Field(default=None, ge=0, le=120)
    status: str | None = None
    is_recurring: bool | None = None
    recurrence_rule: dict[str, Any] | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        """Only 'cancelled' or 'departed' can be set from the client."""
        if v is not None and v not in VALID_CLIENT_STATUSES:
            raise ValueError(
                f"status must be one of {sorted(VALID_CLIENT_STATUSES)}"
            )
        return v

    @field_validator("arrival_time")
    @classmethod
    def validate_future(cls, v: datetime | None) -> datetime | None:
        """Arrival time must be in the future if provided."""
        if v is not None:
            now = datetime.now(timezone.utc)
            compare_v = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
            if compare_v <= now:
                raise ValueError("Arrival time must be in the future")
        return v

    @field_validator("travel_mode")
    @classmethod
    def validate_travel_mode(cls, v: str | None) -> str | None:
        """Travel mode must be a valid option if provided."""
        if v is not None and v not in VALID_TRAVEL_MODES:
            raise ValueError(
                f"travel_mode must be one of {sorted(VALID_TRAVEL_MODES)}"
            )
        return v

    @model_validator(mode="after")
    def validate_origin_group(self) -> "UpdateTripRequest":
        """If any origin field is provided, all three must be provided."""
        origin_fields = [
            self.origin_address,
            self.origin_lat,
            self.origin_lng,
        ]
        provided = [f for f in origin_fields if f is not None]
        if 0 < len(provided) < 3:
            raise ValueError(
                "If any of origin_address, origin_lat, origin_lng is "
                "provided, all three must be provided"
            )
        return self

    @model_validator(mode="after")
    def validate_dest_group(self) -> "UpdateTripRequest":
        """If any dest field is provided, all three must be provided."""
        dest_fields = [self.dest_address, self.dest_lat, self.dest_lng]
        provided = [f for f in dest_fields if f is not None]
        if 0 < len(provided) < 3:
            raise ValueError(
                "If any of dest_address, dest_lat, dest_lng is "
                "provided, all three must be provided"
            )
        return self


class TripResponse(BaseModel):
    """Trip response schema with all fields."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    origin_address: str
    origin_lat: float
    origin_lng: float
    origin_location_id: UUID | None
    origin_is_current_location: bool
    dest_address: str
    dest_lat: float
    dest_lng: float
    dest_location_id: UUID | None
    arrival_time: datetime
    travel_mode: str
    buffer_minutes: int
    status: str
    monitoring_started_at: datetime | None
    last_eta_seconds: int | None
    last_checked_at: datetime | None
    notify_at: datetime | None
    baseline_duration_seconds: int | None
    notified: bool
    notification_count: int
    is_recurring: bool
    recurrence_rule: dict[str, Any] | None
    calendar_event_id: str | None
    created_at: datetime
    updated_at: datetime

    @field_validator("travel_mode", "status", mode="before")
    @classmethod
    def serialize_enum(cls, v: object) -> str:
        """Convert enum values to their string representation."""
        if hasattr(v, "value"):
            return v.value
        return str(v)


class EtaSnapshotResponse(BaseModel):
    """ETA snapshot response for trip detail view."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    checked_at: datetime
    duration_seconds: int
    duration_in_traffic_seconds: int
    traffic_model: str
    congestion_level: str
    distance_meters: int | None

    @field_validator("congestion_level", mode="before")
    @classmethod
    def serialize_enum(cls, v: object) -> str:
        """Convert enum values to their string representation."""
        if hasattr(v, "value"):
            return v.value
        return str(v)


class NotificationResponse(BaseModel):
    """Notification log response for trip detail view."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sent_at: datetime
    type: str
    title: str
    body: str
    eta_at_send_seconds: int | None
    recommended_departure: datetime | None
    delivery_status: str

    @field_validator("type", "delivery_status", mode="before")
    @classmethod
    def serialize_enum(cls, v: object) -> str:
        """Convert enum values to their string representation."""
        if hasattr(v, "value"):
            return v.value
        return str(v)


class TripDetailResponse(TripResponse):
    """Extended trip response with ETA snapshots and notifications."""

    eta_snapshots: list[EtaSnapshotResponse] = []
    notifications: list[NotificationResponse] = []


class PaginatedTripResponse(BaseModel):
    """Paginated list of trips."""

    items: list[TripResponse]
    total: int
    limit: int
    offset: int
