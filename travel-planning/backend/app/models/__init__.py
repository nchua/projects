"""SQLAlchemy models — import all so Alembic can discover them."""

from app.models.device_token import DeviceToken
from app.models.enums import (
    AuthProvider,
    CongestionLevel,
    DeliveryStatus,
    MonitoringPhase,
    NotificationType,
    TravelMode,
    TripStatus,
)
from app.models.notification_log import NotificationLog
from app.models.saved_location import SavedLocation
from app.models.trip import Trip
from app.models.trip_eta_snapshot import TripEtaSnapshot
from app.models.user import User

__all__ = [
    "AuthProvider",
    "CongestionLevel",
    "DeliveryStatus",
    "DeviceToken",
    "MonitoringPhase",
    "NotificationLog",
    "NotificationType",
    "SavedLocation",
    "TravelMode",
    "Trip",
    "TripEtaSnapshot",
    "TripStatus",
    "User",
]
