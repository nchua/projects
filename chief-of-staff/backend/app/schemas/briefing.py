"""Briefing schemas."""

from datetime import date, datetime
from typing import Optional, List, Any, Dict

from pydantic import BaseModel


class BriefingCalendarEvent(BaseModel):
    """A calendar event within a briefing."""

    title: str
    start_time: datetime
    end_time: datetime
    location: Optional[str] = None
    attendees: Optional[List[str]] = None
    needs_prep: bool = False


class BriefingTaskItem(BaseModel):
    """A task item within a briefing."""

    id: str
    title: str
    cadence: str
    priority: str
    streak_count: int = 0
    is_overdue: bool = False


class BriefingActionItem(BaseModel):
    """An action item within a briefing."""

    id: str
    title: str
    source: str
    priority: str
    extracted_deadline: Optional[datetime] = None
    confidence_score: Optional[float] = None


class IntegrationHealthItem(BaseModel):
    """Integration health status within a briefing."""

    provider: str
    status: str
    last_synced_at: Optional[datetime] = None
    error_message: Optional[str] = None


class BriefingMemoryFact(BaseModel):
    """A contextual memory fact surfaced in a briefing."""

    id: str
    fact_text: str
    fact_type: str
    source: str
    people: Optional[List[str]] = None
    valid_until: Optional[datetime] = None
    importance: float = 0.5


class BriefingContent(BaseModel):
    """Structured content for a briefing."""

    calendar_events: List[BriefingCalendarEvent] = []
    overdue_tasks: List[BriefingTaskItem] = []
    todays_tasks: List[BriefingTaskItem] = []
    action_items: List[BriefingActionItem] = []
    integration_health: List[IntegrationHealthItem] = []
    memory_context: List[BriefingMemoryFact] = []
    ai_insights: Optional[str] = None


class BriefingResponse(BaseModel):
    """Schema for briefing in responses."""

    id: str
    briefing_type: str
    date: date
    content: Optional[Dict[str, Any]] = None
    integration_gaps: Optional[List[str]] = None
    generated_at: Optional[datetime] = None
    viewed_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}
