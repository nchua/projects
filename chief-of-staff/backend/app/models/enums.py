"""Application enums stored as String columns (not native PG ENUM)."""

import enum


class Cadence(str, enum.Enum):
    """Recurring task cadence."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"


class MissedBehavior(str, enum.Enum):
    """What happens when a recurring task is missed."""
    ROLL_FORWARD = "roll_forward"
    MARK_MISSED = "mark_missed"


class TaskPriority(str, enum.Enum):
    """Priority level for recurring tasks."""
    NON_NEGOTIABLE = "non_negotiable"
    FLEXIBLE = "flexible"


class ActionItemSource(str, enum.Enum):
    """Source of an AI-extracted action item."""
    GMAIL = "gmail"
    GITHUB = "github"
    SLACK = "slack"
    NOTION = "notion"
    DISCORD = "discord"
    MANUAL = "manual"


class ActionItemPriority(str, enum.Enum):
    """Priority level for action items."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ActionItemStatus(str, enum.Enum):
    """Status of an action item."""
    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    ACTIONED = "actioned"
    DISMISSED = "dismissed"


class DismissReason(str, enum.Enum):
    """Reason for dismissing an action item."""
    NOT_ACTION_ITEM = "not_action_item"
    ALREADY_DONE = "already_done"
    NOT_RELEVANT = "not_relevant"


class TriggerType(str, enum.Enum):
    """Trigger type for one-off reminders."""
    TIME = "time"
    LOCATION = "location"
    CONTEXT = "context"
    FOLLOW_UP = "follow_up"


class ReminderStatus(str, enum.Enum):
    """Status of a one-off reminder."""
    PENDING = "pending"
    COMPLETED = "completed"
    DISMISSED = "dismissed"


class BriefingType(str, enum.Enum):
    """Type of briefing."""
    MORNING = "morning"


class IntegrationProvider(str, enum.Enum):
    """Supported integration providers."""
    GOOGLE_CALENDAR = "google_calendar"
    GMAIL = "gmail"
    GITHUB = "github"
    SLACK = "slack"
    NOTION = "notion"
    DISCORD = "discord"
    APPLE_CALENDAR = "apple_calendar"


class IntegrationStatus(str, enum.Enum):
    """Health status of an integration."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    DISABLED = "disabled"


class ResourceType(str, enum.Enum):
    """Type of resource being synced."""
    INBOX = "inbox"
    CALENDAR = "calendar"
    CHANNELS = "channels"
    NOTIFICATIONS = "notifications"


class SyncStatus(str, enum.Enum):
    """Status of a sync operation."""
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


class CalendarProvider(str, enum.Enum):
    """Calendar event provider."""
    GOOGLE = "google"
    APPLE = "apple"


class NotificationType(str, enum.Enum):
    """Type of notification sent."""
    BRIEFING = "briefing"
    TASK_REMINDER = "task_reminder"
    NUDGE = "nudge"


class NotificationChannel(str, enum.Enum):
    """Channel used to deliver a notification."""
    PUSH = "push"
    LOCAL = "local"
