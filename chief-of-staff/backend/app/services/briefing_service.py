"""Briefing engine — hybrid rule-based assembly + AI insights.

Per spec: Briefing always generates with available data. Missing
sources are flagged in integration_gaps, never silently omitted.
"""

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import anthropic
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.action_item import ActionItem
from app.models.briefing import Briefing
from app.models.calendar_event import CalendarEvent
from app.models.integration import Integration
from app.models.one_off_reminder import OneOffReminder
from app.models.recurring_task import RecurringTask, TaskCompletion
from app.schemas.briefing import (
    BriefingActionItem,
    BriefingCalendarEvent,
    BriefingContent,
    BriefingMemoryFact,
    BriefingTaskItem,
    IntegrationHealthItem,
)
from app.services.audit_log import log_audit
from app.services.memory_service import get_relevant_memories
from app.services.prioritization_service import rerank_action_items

logger = logging.getLogger(__name__)

AI_INSIGHTS_MODEL = "claude-sonnet-4-5-20250514"

_INSIGHTS_SYSTEM = """\
You are a concise personal assistant. Given a structured summary \
of someone's day (calendar, tasks, action items, and context from \
recent messages/meetings), provide:

1. **Priority ranking**: What to focus on first and why (2-3 items)
2. **Risk flags**: Anything at risk of falling through the cracks — \
especially approaching deadlines and commitments due from context
3. **Suggested focus**: One sentence on what makes today successful

Be brief and actionable. No fluff. Use bullet points."""

_INSIGHTS_USER = """\
Here is my day overview for {date}:

Calendar ({event_count} events):
{calendar_summary}

Recurring tasks ({task_count} due today, {overdue_count} overdue):
{task_summary}

Action items ({action_count} open):
{action_summary}

Context from recent messages/meetings ({memory_count} items):
{memory_summary}

Give me a brief morning briefing with priorities, risks, and \
focus for today."""


def generate_morning_briefing(
    user_id: str,
    db: Session,
    target_date: date | None = None,
) -> Briefing:
    """Generate a morning briefing for the user.

    Uses hybrid approach: rule-based assembly for structured data,
    Claude Sonnet for priority ranking and insights.

    Args:
        user_id: The user to generate for.
        db: Database session.
        target_date: Date to generate for (defaults to today).

    Returns:
        The generated (or existing) Briefing record.
    """
    if target_date is None:
        target_date = date.today()

    # Check if briefing already exists for this date
    existing = (
        db.query(Briefing)
        .filter(
            Briefing.user_id == user_id,
            Briefing.date == target_date,
        )
        .first()
    )
    if existing and existing.content:
        return existing

    # === Rule-based assembly ===
    calendar_events = _get_calendar_events(
        db, user_id, target_date
    )
    overdue_tasks = _get_overdue_tasks(db, user_id, target_date)
    todays_tasks = _get_todays_tasks(db, user_id, target_date)
    action_items = _get_open_action_items(db, user_id)
    integration_health = _get_integration_health(db, user_id)

    # === Memory context (Mem0 + Zep pattern) ===
    memory_context = _get_memory_context(db, user_id, target_date)

    # Identify integration gaps
    integration_gaps = [
        h.provider
        for h in integration_health
        if h.status in ("failed", "degraded")
    ]

    # === AI insights (optional, graceful degradation) ===
    ai_insights = _generate_ai_insights(
        calendar_events,
        overdue_tasks,
        todays_tasks,
        action_items,
        memory_context,
        target_date,
        user_id,
        db,
    )

    # === Assemble content ===
    content = BriefingContent(
        calendar_events=calendar_events,
        overdue_tasks=overdue_tasks,
        todays_tasks=todays_tasks,
        action_items=action_items,
        integration_health=integration_health,
        memory_context=memory_context,
        ai_insights=ai_insights,
    )

    # === Persist ===
    now = datetime.now(tz=timezone.utc)

    if existing:
        existing.content = content.model_dump(mode="json")
        existing.integration_gaps = integration_gaps
        existing.generated_at = now
        briefing = existing
    else:
        briefing = Briefing(
            user_id=user_id,
            briefing_type="morning",
            date=target_date,
            content=content.model_dump(mode="json"),
            integration_gaps=integration_gaps,
            generated_at=now,
        )
        db.add(briefing)

    db.flush()
    return briefing


# =============================================================================
# DATA ASSEMBLY (rule-based, no AI)
# =============================================================================


def _get_calendar_events(
    db: Session, user_id: str, target_date: date
) -> list[BriefingCalendarEvent]:
    """Get calendar events for the target date."""
    day_start = datetime.combine(target_date, time.min).replace(
        tzinfo=timezone.utc
    )
    day_end = datetime.combine(
        target_date, time.max
    ).replace(tzinfo=timezone.utc)

    events = (
        db.query(CalendarEvent)
        .filter(
            CalendarEvent.user_id == user_id,
            CalendarEvent.start_time >= day_start,
            CalendarEvent.start_time <= day_end,
        )
        .order_by(CalendarEvent.start_time)
        .all()
    )

    return [
        BriefingCalendarEvent(
            title=e.title or "(No title)",
            start_time=e.start_time,
            end_time=e.end_time,
            location=e.location,
            attendees=(
                [a.get("name") or a.get("email", "")
                 for a in (e.attendees or [])]
            ),
            needs_prep=e.needs_prep,
        )
        for e in events
    ]


def _get_overdue_tasks(
    db: Session, user_id: str, target_date: date
) -> list[BriefingTaskItem]:
    """Get overdue recurring tasks (roll_forward, not completed)."""
    tasks = (
        db.query(RecurringTask)
        .filter(
            RecurringTask.user_id == user_id,
            RecurringTask.is_archived.is_(False),
            RecurringTask.missed_behavior == "roll_forward",
        )
        .all()
    )

    overdue = []
    for task in tasks:
        # Check if completed today or recently
        recent_completion = (
            db.query(TaskCompletion)
            .filter(
                TaskCompletion.recurring_task_id == task.id,
                TaskCompletion.date >= target_date - timedelta(days=1),
                TaskCompletion.completed_at.isnot(None),
            )
            .first()
        )
        if recent_completion:
            continue

        # Determine if overdue based on last completion
        if task.last_completed_at:
            days_since = (
                target_date
                - task.last_completed_at.date()
            ).days
            if task.cadence == "daily" and days_since > 1:
                overdue.append(
                    BriefingTaskItem(
                        id=task.id,
                        title=task.title,
                        cadence=task.cadence,
                        priority=task.priority,
                        streak_count=task.streak_count,
                        is_overdue=True,
                    )
                )

    return overdue


def _get_todays_tasks(
    db: Session, user_id: str, target_date: date
) -> list[BriefingTaskItem]:
    """Get recurring tasks due today."""
    tasks = (
        db.query(RecurringTask)
        .filter(
            RecurringTask.user_id == user_id,
            RecurringTask.is_archived.is_(False),
        )
        .order_by(RecurringTask.sort_order)
        .all()
    )

    day_of_week = target_date.weekday()  # 0=Mon, 6=Sun
    day_of_month = target_date.day

    due_today = []
    for task in tasks:
        is_due = False
        if task.cadence == "daily":
            is_due = True
        elif task.cadence == "weekly" and day_of_week == 0:
            # Default: weekly tasks due on Monday
            is_due = True
        elif task.cadence == "monthly" and day_of_month == 1:
            # Default: monthly tasks due on 1st
            is_due = True

        if not is_due:
            continue

        due_today.append(
            BriefingTaskItem(
                id=task.id,
                title=task.title,
                cadence=task.cadence,
                priority=task.priority,
                streak_count=task.streak_count,
                is_overdue=False,
            )
        )

    return due_today


def _get_open_action_items(
    db: Session, user_id: str
) -> list[BriefingActionItem]:
    """Get open action items sorted by composite score (RFM-based)."""
    items = (
        db.query(ActionItem)
        .filter(
            ActionItem.user_id == user_id,
            ActionItem.status.in_(["new", "acknowledged"]),
        )
        .order_by(ActionItem.created_at.desc())
        .limit(20)
        .all()
    )

    # Rerank by composite score (contact importance + deadline urgency + source reliability)
    ranked = rerank_action_items(items, user_id, db)

    return [
        BriefingActionItem(
            id=item.id,
            title=item.title,
            source=item.source,
            priority=item.priority,
            extracted_deadline=item.extracted_deadline,
            confidence_score=item.confidence_score,
        )
        for item in ranked[:10]  # Top 10 for the briefing
    ]


def _get_memory_context(
    db: Session, user_id: str, target_date: date
) -> list[BriefingMemoryFact]:
    """Get relevant memory facts for the briefing."""
    facts = get_relevant_memories(user_id, target_date, db, limit=10)

    return [
        BriefingMemoryFact(
            id=fact.id,
            fact_text=fact.fact_text,
            fact_type=fact.fact_type,
            source=fact.source,
            people=fact.people,
            valid_until=fact.valid_until,
            importance=fact.importance,
        )
        for fact in facts
    ]


def _get_integration_health(
    db: Session, user_id: str
) -> list[IntegrationHealthItem]:
    """Get health status of all active integrations."""
    integrations = (
        db.query(Integration)
        .filter(
            Integration.user_id == user_id,
            Integration.is_active.is_(True),
        )
        .all()
    )

    return [
        IntegrationHealthItem(
            provider=i.provider,
            status=i.status,
            last_synced_at=i.last_synced_at,
            error_message=i.last_error,
        )
        for i in integrations
    ]


def _get_pending_reminders(
    db: Session, user_id: str, target_date: date
) -> list[dict[str, Any]]:
    """Get pending one-off reminders for today."""
    reminders = (
        db.query(OneOffReminder)
        .filter(
            OneOffReminder.user_id == user_id,
            OneOffReminder.status == "pending",
        )
        .all()
    )

    # Filter to reminders due today (time-based triggers)
    due_today = []
    for r in reminders:
        config = r.trigger_config or {}
        if r.trigger_type == "time":
            trigger_date = config.get("date")
            if trigger_date and str(trigger_date) == str(target_date):
                due_today.append({
                    "id": r.id,
                    "title": r.title,
                    "trigger_time": config.get("time"),
                })
        else:
            # Non-time reminders (follow-up, etc.) always shown
            due_today.append({
                "id": r.id,
                "title": r.title,
            })

    return due_today


# =============================================================================
# AI INSIGHTS (Claude Sonnet)
# =============================================================================


def _generate_ai_insights(
    calendar_events: list[BriefingCalendarEvent],
    overdue_tasks: list[BriefingTaskItem],
    todays_tasks: list[BriefingTaskItem],
    action_items: list[BriefingActionItem],
    memory_context: list[BriefingMemoryFact],
    target_date: date,
    user_id: str,
    db: Session,
) -> str | None:
    """Generate AI-powered priority ranking and risk flags.

    Returns None if AI is unavailable (graceful degradation).
    """
    settings = get_settings()
    if not settings.anthropic_api_key:
        return None

    # Build summaries for the prompt
    cal_lines = []
    for e in calendar_events:
        t = e.start_time.strftime("%H:%M")
        cal_lines.append(f"- {t} {e.title}")
    calendar_summary = (
        "\n".join(cal_lines) if cal_lines else "No events"
    )

    task_lines = []
    for t in overdue_tasks:
        task_lines.append(f"- [OVERDUE] {t.title} ({t.priority})")
    for t in todays_tasks:
        task_lines.append(
            f"- {t.title} ({t.priority}, {t.streak_count}d streak)"
        )
    task_summary = (
        "\n".join(task_lines) if task_lines else "No tasks"
    )

    action_lines = []
    for a in action_items:
        deadline = (
            f" (due {a.extracted_deadline})"
            if a.extracted_deadline
            else ""
        )
        action_lines.append(
            f"- [{a.priority}] {a.title} (from {a.source}){deadline}"
        )
    action_summary = (
        "\n".join(action_lines) if action_lines else "No items"
    )

    # Build memory context summary
    memory_lines = []
    for m in memory_context:
        deadline_str = (
            f" (expires {m.valid_until.strftime('%Y-%m-%d')})"
            if m.valid_until
            else ""
        )
        memory_lines.append(
            f"- [{m.fact_type}] {m.fact_text} (from {m.source}){deadline_str}"
        )
    memory_summary = (
        "\n".join(memory_lines) if memory_lines else "No context"
    )

    user_prompt = _INSIGHTS_USER.format(
        date=target_date.isoformat(),
        event_count=len(calendar_events),
        calendar_summary=calendar_summary,
        task_count=len(todays_tasks),
        overdue_count=len(overdue_tasks),
        task_summary=task_summary,
        action_count=len(action_items),
        action_summary=action_summary,
        memory_count=len(memory_context),
        memory_summary=memory_summary,
    )

    try:
        client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key
        )
        response = client.messages.create(
            model=AI_INSIGHTS_MODEL,
            max_tokens=512,
            system=_INSIGHTS_SYSTEM,
            messages=[{"role": "user", "content": user_prompt}],
        )

        insights = response.content[0].text

        log_audit(
            db,
            "ai_briefing_insights",
            user_id=user_id,
            metadata={"date": target_date.isoformat()},
        )

        return insights

    except Exception as e:
        logger.warning("AI insights generation failed: %s", e)
        log_audit(
            db,
            "ai_briefing_insights",
            user_id=user_id,
            success=False,
            error_details=str(e),
        )
        return None
