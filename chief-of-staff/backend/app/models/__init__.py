"""Import all models so Alembic can discover them."""

from app.models.user import User  # noqa: F401
from app.models.recurring_task import RecurringTask, TaskCompletion  # noqa: F401
from app.models.action_item import ActionItem  # noqa: F401
from app.models.contact import Contact, ActionItemContact  # noqa: F401
from app.models.one_off_reminder import OneOffReminder  # noqa: F401
from app.models.briefing import Briefing  # noqa: F401
from app.models.integration import Integration  # noqa: F401
from app.models.sync_state import SyncState  # noqa: F401
from app.models.calendar_event import CalendarEvent  # noqa: F401
from app.models.notification import DeviceToken, NotificationLog  # noqa: F401
from app.models.audit_log import AuditLog  # noqa: F401
from app.models.memory_fact import MemoryFact  # noqa: F401
