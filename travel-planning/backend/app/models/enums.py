"""Database enum definitions."""

import enum


class MonitoringPhase(str, enum.Enum):
    dormant = "dormant"
    passive = "passive"
    active = "active"
    critical = "critical"
    departed = "departed"


class TravelMode(str, enum.Enum):
    driving = "driving"
    transit = "transit"
    walking = "walking"
    cycling = "cycling"


class TripStatus(str, enum.Enum):
    pending = "pending"
    monitoring = "monitoring"
    notified = "notified"
    departed = "departed"
    completed = "completed"
    cancelled = "cancelled"


class CongestionLevel(str, enum.Enum):
    unknown = "unknown"
    light = "light"
    moderate = "moderate"
    heavy = "heavy"
    severe = "severe"


class NotificationType(str, enum.Enum):
    heads_up = "heads_up"
    prepare = "prepare"
    leave_soon = "leave_soon"
    leave_now = "leave_now"
    running_late = "running_late"


class DeliveryStatus(str, enum.Enum):
    pending = "pending"
    delivered = "delivered"
    failed = "failed"
    dismissed = "dismissed"
    tapped = "tapped"


class AuthProvider(str, enum.Enum):
    email = "email"
    apple = "apple"
