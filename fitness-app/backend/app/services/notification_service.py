"""
Push notification service — sends APNs notifications and manages preferences
"""
import logging
import os
from typing import Optional
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.notification import (
    DeviceToken, NotificationPreference, NotificationType,
    SERVER_SENT_TYPES
)

logger = logging.getLogger(__name__)


def get_apns_client():
    """Lazy-initialize the APNs client. Returns None if not configured."""
    key_id = os.environ.get("APNS_KEY_ID")
    team_id = os.environ.get("APNS_TEAM_ID")
    auth_key_path = os.environ.get("APNS_AUTH_KEY_PATH")

    if not all([key_id, team_id, auth_key_path]):
        logger.debug("APNs not configured — skipping push notification")
        return None

    try:
        from aioapns import APNs, NotificationRequest
        use_sandbox = os.environ.get("APNS_USE_SANDBOX", "true").lower() == "true"
        client = APNs(
            key=auth_key_path,
            key_id=key_id,
            team_id=team_id,
            topic=os.environ.get("APNS_TOPIC", "com.nickchua.fitnessapp"),
            use_sandbox=use_sandbox,
        )
        return client
    except Exception as e:
        logger.error(f"Failed to initialize APNs client: {e}")
        return None


def is_notification_enabled(
    db: Session,
    user_id: str,
    notification_type: NotificationType,
) -> bool:
    """Check if a notification type is enabled for a user (defaults to True)."""
    pref = db.query(NotificationPreference).filter(
        NotificationPreference.user_id == user_id,
        NotificationPreference.notification_type == notification_type.value,
    ).first()
    if pref is None:
        return True  # Default enabled
    return pref.enabled


def get_active_tokens(db: Session, user_id: str) -> list[DeviceToken]:
    """Get all active device tokens for a user."""
    return db.query(DeviceToken).filter(
        DeviceToken.user_id == user_id,
        DeviceToken.is_active == True,
    ).all()


async def send_push_notification(
    db: Session,
    user_id: str,
    notification_type: NotificationType,
    title: str,
    body: str,
    data: Optional[dict] = None,
) -> bool:
    """
    Send a push notification to a user if their preference allows it.

    Returns True if notification was sent (or attempted), False if skipped.
    """
    # Only send server-sent types via APNs
    if notification_type not in SERVER_SENT_TYPES:
        logger.debug(f"Skipping APNs for local notification type: {notification_type}")
        return False

    # Check user preference
    if not is_notification_enabled(db, user_id, notification_type):
        logger.debug(f"Notification {notification_type} disabled for user {user_id}")
        return False

    # Get active tokens
    tokens = get_active_tokens(db, user_id)
    if not tokens:
        logger.debug(f"No active device tokens for user {user_id}")
        return False

    client = get_apns_client()
    if client is None:
        logger.info(f"APNs not configured — would send '{title}' to user {user_id}")
        return False

    try:
        from aioapns import NotificationRequest

        alert_data = {"title": title, "body": body}
        payload = {"aps": {"alert": alert_data, "sound": "default"}}
        if data:
            payload["custom"] = data

        for token_record in tokens:
            try:
                request = NotificationRequest(
                    device_token=token_record.token,
                    message=payload,
                )
                response = await client.send_notification(request)
                if not response.is_successful:
                    logger.warning(
                        f"APNs error for token {token_record.token[:8]}...: "
                        f"{response.description}"
                    )
                    # Mark invalid tokens as inactive
                    if response.description in (
                        "BadDeviceToken", "Unregistered", "ExpiredToken"
                    ):
                        token_record.is_active = False
                        db.commit()
            except Exception as e:
                logger.error(f"Failed to send to token {token_record.token[:8]}...: {e}")

        return True
    except Exception as e:
        logger.error(f"APNs send failed: {e}")
        return False


# ── Convenience wrappers ──────────────────────────────────────────

async def notify_friend_request_received(
    db: Session, receiver_id: str, sender_name: str
) -> bool:
    """Notify user that someone sent them a friend request."""
    return await send_push_notification(
        db, receiver_id,
        NotificationType.FRIEND_REQUEST_RECEIVED,
        "NEW ALLY REQUEST",
        f"{sender_name} wants to join your party.",
        data={"type": "friend_request_received"},
    )


async def notify_friend_request_accepted(
    db: Session, sender_id: str, accepter_name: str
) -> bool:
    """Notify original sender that their request was accepted."""
    return await send_push_notification(
        db, sender_id,
        NotificationType.FRIEND_REQUEST_ACCEPTED,
        "ALLY JOINED",
        f"{accepter_name} accepted your request. Your party grows stronger.",
        data={"type": "friend_request_accepted"},
    )


async def notify_achievement_unlocked(
    db: Session, user_id: str, achievement_name: str, description: str
) -> bool:
    """Notify user of a new achievement."""
    return await send_push_notification(
        db, user_id,
        NotificationType.ACHIEVEMENT_UNLOCKED,
        "ACHIEVEMENT UNLOCKED",
        f"{achievement_name} \u2014 {description}",
        data={"type": "achievement_unlocked"},
    )


async def notify_level_up(
    db: Session, user_id: str, new_level: int
) -> bool:
    """Notify user they leveled up."""
    return await send_push_notification(
        db, user_id,
        NotificationType.LEVEL_UP,
        "LEVEL UP!",
        f"You've reached Level {new_level}. Keep pushing your limits.",
        data={"type": "level_up", "level": new_level},
    )


async def notify_rank_promotion(
    db: Session, user_id: str, new_rank: str
) -> bool:
    """Notify user of rank promotion."""
    rank_display = new_rank.upper() if new_rank else "UNKNOWN"
    return await send_push_notification(
        db, user_id,
        NotificationType.RANK_PROMOTION,
        "RANK UP!",
        f"You've been promoted to {rank_display}-Rank Warrior. New abilities unlocked.",
        data={"type": "rank_promotion", "rank": new_rank},
    )


async def notify_dungeon_spawned(
    db: Session, user_id: str, dungeon_name: str, dungeon_rank: str
) -> bool:
    """Notify user a new dungeon has appeared."""
    return await send_push_notification(
        db, user_id,
        NotificationType.DUNGEON_SPAWNED,
        "GATE DETECTED",
        f"{dungeon_rank}-Rank Dungeon \"{dungeon_name}\" has appeared.",
        data={"type": "dungeon_spawned"},
    )


async def notify_weekly_report_ready(db: Session, user_id: str) -> bool:
    """Notify user their weekly report is available."""
    return await send_push_notification(
        db, user_id,
        NotificationType.WEEKLY_REPORT_READY,
        "WEEKLY REPORT",
        "Your weekly progress report is ready. Review your performance.",
        data={"type": "weekly_report_ready"},
    )


async def notify_mission_offered(db: Session, user_id: str) -> bool:
    """Notify user a new weekly mission is available."""
    return await send_push_notification(
        db, user_id,
        NotificationType.MISSION_OFFERED,
        "NEW MISSION",
        "This week's training mission is ready. Accept it to continue your journey.",
        data={"type": "mission_offered"},
    )
