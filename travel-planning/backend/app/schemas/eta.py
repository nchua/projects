"""ETA-related Pydantic schemas."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.models.enums import CongestionLevel


class EtaResult(BaseModel):
    """Parsed result from a traffic API route computation."""

    duration_seconds: int = Field(
        description="Static duration without traffic (seconds)"
    )
    duration_in_traffic_seconds: int = Field(
        description="Duration with current traffic (seconds)"
    )
    distance_meters: int = Field(description="Route distance in meters")
    congestion_level: CongestionLevel = Field(
        default=CongestionLevel.unknown,
        description="Computed congestion level from traffic ratio",
    )
    traffic_ratio: float = Field(
        description="Ratio of traffic duration to static duration"
    )

    @classmethod
    def from_route_response(
        cls,
        duration_seconds: int,
        duration_in_traffic_seconds: int,
        distance_meters: int,
    ) -> EtaResult:
        """Create an EtaResult computing congestion from the traffic ratio."""
        if duration_seconds <= 0:
            traffic_ratio = 1.0
        else:
            traffic_ratio = duration_in_traffic_seconds / duration_seconds

        if traffic_ratio < 1.1:
            congestion = CongestionLevel.light
        elif traffic_ratio < 1.3:
            congestion = CongestionLevel.moderate
        elif traffic_ratio < 1.6:
            congestion = CongestionLevel.heavy
        else:
            congestion = CongestionLevel.severe

        return cls(
            duration_seconds=duration_seconds,
            duration_in_traffic_seconds=duration_in_traffic_seconds,
            distance_meters=distance_meters,
            congestion_level=congestion,
            traffic_ratio=round(traffic_ratio, 3),
        )

    def to_cache_dict(self) -> dict:
        """Serialize for Redis cache storage."""
        return {
            "duration": self.duration_seconds,
            "static_duration": self.duration_seconds,
            "duration_in_traffic": self.duration_in_traffic_seconds,
            "distance_meters": self.distance_meters,
            "congestion": self.congestion_level.value,
            "traffic_ratio": self.traffic_ratio,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    def from_cache(cls, data: dict) -> EtaResult:
        """Deserialize from Redis cache."""
        return cls(
            duration_seconds=data["duration"],
            duration_in_traffic_seconds=data["duration_in_traffic"],
            distance_meters=data.get("distance_meters", 0),
            congestion_level=CongestionLevel(data["congestion"]),
            traffic_ratio=data.get("traffic_ratio", 1.0),
        )
