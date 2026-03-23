"""Contextual memory service — extract, store, query, decay.

Combines:
- Mem0's ADD/UPDATE/NOOP pattern for fact lifecycle
- Zep/Graphiti's bi-temporal timestamps for validity tracking
- Structured SQL (no embeddings for v1)

Extraction uses Haiku (~$0.0002/msg) for cost efficiency.
"""

import hashlib
import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import anthropic
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.memory_fact import MemoryFact
from app.services.audit_log import log_audit

logger = logging.getLogger(__name__)

MEMORY_EXTRACTION_MODEL = "claude-haiku-4-5-20251001"

# Decay parameters
DECAY_RATE = 0.01  # importance *= exp(-DECAY_RATE * days_since_access)
ARCHIVE_THRESHOLD = 0.05  # archive facts with importance below this

_MEMORY_EXTRACTION_SYSTEM = """\
Extract KEY FACTS worth remembering across sessions from the given text.
Focus on: commitments, deadlines, decisions, context, follow-ups.
Max 3 facts per message. Skip trivial details.

For each fact return:
- fact_text: concise description (max 120 chars)
- fact_type: one of "commitment", "deadline", "decision", "context", "follow_up"
- people: list of names or emails mentioned (empty list if none)
- valid_from: ISO date when this fact became true (best guess, use today if unclear)
- valid_until: ISO date when this fact expires (null if ongoing/indefinite)
- importance: 0.0-1.0 (1.0 = critical deadline, 0.1 = minor context)
- confidence: 0.0-1.0 extraction confidence

Return JSON: {"facts": [...]}
If no meaningful facts, return: {"facts": []}"""


async def extract_memory_facts(
    text: str,
    source: str,
    source_id: str,
    source_url: str,
) -> list[dict[str, Any]]:
    """Extract memory facts from text using Haiku.

    Args:
        text: The message/meeting text to extract from.
        source: Source identifier (gmail, slack, granola, etc.).
        source_id: Source-specific ID.
        source_url: URL to source content.

    Returns:
        List of fact dicts ready for persist_memory_facts.
    """
    settings = get_settings()
    if not settings.anthropic_api_key:
        return []

    # Truncate to avoid excessive token usage
    truncated = text[:3000] if len(text) > 3000 else text

    try:
        client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key
        )
        response = await client.messages.create(
            model=MEMORY_EXTRACTION_MODEL,
            max_tokens=512,
            system=_MEMORY_EXTRACTION_SYSTEM,
            messages=[{
                "role": "user",
                "content": (
                    f"Source: {source}\n"
                    f"Today's date: {date.today().isoformat()}\n\n"
                    f"{truncated}"
                ),
            }],
        )

        raw = response.content[0].text
        parsed = json.loads(raw)
        facts = parsed.get("facts", [])

        # Attach source metadata to each fact
        for fact in facts:
            fact["source"] = source
            fact["source_id"] = source_id
            fact["source_url"] = source_url

        return facts[:3]  # Hard cap at 3

    except Exception as e:
        logger.warning("Memory fact extraction failed: %s", e)
        return []


async def persist_memory_facts_async(
    facts: list[dict[str, Any]],
    user_id: str,
    session: AsyncSession,
) -> list[MemoryFact]:
    """Persist extracted facts using Mem0-style CRUD (async version).

    For each new fact:
    1. Find similar existing active facts (by dedup_hash, people overlap)
    2. Classify: ADD (new) / UPDATE (supersede old) / NOOP (already known)
    3. On UPDATE: mark old fact inactive, create new with superseded_by link
    """
    created = []
    now = datetime.now(tz=timezone.utc)

    for fact_data in facts:
        fact_text = fact_data.get("fact_text", "")
        if not fact_text:
            continue

        people = fact_data.get("people", [])
        fact_type = fact_data.get("fact_type", "context")

        # Generate dedup hash
        dedup = _fact_dedup_hash(fact_text, people)

        # Check for existing similar fact by dedup hash
        existing_result = await session.execute(
            select(MemoryFact).where(
                MemoryFact.user_id == user_id,
                MemoryFact.dedup_hash == dedup,
                MemoryFact.is_active.is_(True),
            )
        )
        existing = existing_result.scalar_one_or_none()

        # If no exact match, try people overlap + fact_type
        if not existing and people:
            existing = await _find_similar_fact_async(
                session, user_id, fact_type, people
            )

        if existing:
            # NOOP if text is very similar
            if _texts_match(existing.fact_text, fact_text):
                continue

            # UPDATE: supersede old fact
            existing.is_active = False
            existing.invalidated_at = now

        # Parse dates
        valid_from = _parse_date(
            fact_data.get("valid_from"), default=now
        )
        valid_until = _parse_date(
            fact_data.get("valid_until"), default=None
        )

        new_fact = MemoryFact(
            user_id=user_id,
            fact_text=fact_text[:500],
            fact_type=fact_data.get("fact_type", "context"),
            source=fact_data.get("source", "unknown"),
            source_id=fact_data.get("source_id"),
            source_url=fact_data.get("source_url"),
            people=fact_data.get("people"),
            valid_from=valid_from,
            valid_until=valid_until,
            extracted_at=now,
            importance=float(fact_data.get("importance", 0.5)),
            confidence=float(fact_data.get("confidence", 0.5)),
            dedup_hash=dedup,
            superseded_by_id=None,
            is_active=True,
        )

        # Link old → new if updating
        if existing:
            session.add(new_fact)
            await session.flush()
            existing.superseded_by_id = new_fact.id
        else:
            session.add(new_fact)

        created.append(new_fact)

    return created


def persist_memory_facts(
    facts: list[dict[str, Any]],
    user_id: str,
    db: Session,
) -> list[MemoryFact]:
    """Persist extracted facts using Mem0-style CRUD (sync version).

    Used by API endpoints for manual fact creation.
    """
    created = []
    now = datetime.now(tz=timezone.utc)

    for fact_data in facts:
        fact_text = fact_data.get("fact_text", "")
        if not fact_text:
            continue

        people = fact_data.get("people", [])
        fact_type = fact_data.get("fact_type", "context")
        dedup = _fact_dedup_hash(fact_text, people)

        # Try exact dedup match first
        existing = (
            db.query(MemoryFact)
            .filter(
                MemoryFact.user_id == user_id,
                MemoryFact.dedup_hash == dedup,
                MemoryFact.is_active.is_(True),
            )
            .first()
        )

        # If no exact match, try people overlap + fact_type match
        if not existing and people:
            existing = _find_similar_fact(
                db, user_id, fact_type, people
            )

        if existing:
            if _texts_match(existing.fact_text, fact_text):
                continue
            existing.is_active = False
            existing.invalidated_at = now

        valid_from = _parse_date(
            fact_data.get("valid_from"), default=now
        )
        valid_until = _parse_date(
            fact_data.get("valid_until"), default=None
        )

        new_fact = MemoryFact(
            user_id=user_id,
            fact_text=fact_text[:500],
            fact_type=fact_data.get("fact_type", "context"),
            source=fact_data.get("source", "manual"),
            source_id=fact_data.get("source_id"),
            source_url=fact_data.get("source_url"),
            people=fact_data.get("people"),
            valid_from=valid_from,
            valid_until=valid_until,
            extracted_at=now,
            importance=float(fact_data.get("importance", 0.5)),
            confidence=float(fact_data.get("confidence", 0.5)),
            dedup_hash=dedup,
            is_active=True,
        )

        if existing:
            db.add(new_fact)
            db.flush()
            existing.superseded_by_id = new_fact.id
        else:
            db.add(new_fact)

        created.append(new_fact)

    db.flush()
    return created


def get_relevant_memories(
    user_id: str,
    target_date: date,
    db: Session,
    limit: int = 15,
) -> list[MemoryFact]:
    """Query active memory facts relevant to a target date.

    Retrieves facts where:
    - is_active = True
    - valid_from <= target_date + 2 days (include near-future)
    - valid_until is NULL or >= target_date - 1 day

    Ordered by importance descending. Increments access_count.
    """
    now = datetime.now(tz=timezone.utc)
    target_dt = datetime.combine(target_date, datetime.min.time()).replace(
        tzinfo=timezone.utc
    )
    window_start = target_dt - timedelta(days=1)
    window_end = target_dt + timedelta(days=2)

    facts = (
        db.query(MemoryFact)
        .filter(
            MemoryFact.user_id == user_id,
            MemoryFact.is_active.is_(True),
            MemoryFact.valid_from <= window_end,
        )
        .filter(
            (MemoryFact.valid_until.is_(None))
            | (MemoryFact.valid_until >= window_start)
        )
        .order_by(MemoryFact.importance.desc())
        .limit(limit)
        .all()
    )

    # Increment access count
    for fact in facts:
        fact.access_count = (fact.access_count or 0) + 1
        fact.last_accessed_at = now

    db.flush()
    return facts


async def decay_and_cleanup(ctx: dict[str, Any]) -> None:
    """Daily cron: apply importance decay and archive stale facts.

    importance *= exp(-DECAY_RATE * days_since_access)
    Archive facts with importance < ARCHIVE_THRESHOLD.
    """
    import math

    session_factory = ctx["db_session"]
    now = datetime.now(tz=timezone.utc)

    async with session_factory() as session:
        # Get all active facts
        result = await session.execute(
            select(MemoryFact).where(MemoryFact.is_active.is_(True))
        )
        facts = result.scalars().all()

        archived_count = 0
        for fact in facts:
            last_access = fact.last_accessed_at or fact.extracted_at
            if last_access.tzinfo is None:
                last_access = last_access.replace(tzinfo=timezone.utc)
            days_since = max((now - last_access).days, 0)

            decay_factor = math.exp(-DECAY_RATE * days_since)
            new_importance = fact.importance * decay_factor

            if new_importance < ARCHIVE_THRESHOLD:
                fact.is_active = False
                fact.invalidated_at = now
                archived_count += 1
            else:
                fact.importance = round(new_importance, 4)

        await session.commit()

    logger.info(
        "Memory decay: processed %d facts, archived %d",
        len(facts),
        archived_count,
    )


# =============================================================================
# HELPERS
# =============================================================================


def _find_similar_fact(
    db: Session,
    user_id: str,
    fact_type: str,
    people: list[str],
) -> MemoryFact | None:
    """Find an active fact with matching fact_type and people overlap."""
    candidates = (
        db.query(MemoryFact)
        .filter(
            MemoryFact.user_id == user_id,
            MemoryFact.fact_type == fact_type,
            MemoryFact.is_active.is_(True),
            MemoryFact.people.isnot(None),
        )
        .all()
    )

    people_lower = {p.lower() for p in people}
    for candidate in candidates:
        if not candidate.people:
            continue
        candidate_people = {p.lower() for p in candidate.people}
        if people_lower & candidate_people:  # Any overlap
            return candidate

    return None


async def _find_similar_fact_async(
    session: AsyncSession,
    user_id: str,
    fact_type: str,
    people: list[str],
) -> MemoryFact | None:
    """Find an active fact with matching fact_type and people overlap (async)."""
    result = await session.execute(
        select(MemoryFact).where(
            MemoryFact.user_id == user_id,
            MemoryFact.fact_type == fact_type,
            MemoryFact.is_active.is_(True),
            MemoryFact.people.isnot(None),
        )
    )
    candidates = result.scalars().all()

    people_lower = {p.lower() for p in people}
    for candidate in candidates:
        if not candidate.people:
            continue
        candidate_people = {p.lower() for p in candidate.people}
        if people_lower & candidate_people:
            return candidate

    return None


def _fact_dedup_hash(fact_text: str, people: list[str] | None) -> str:
    """Generate a dedup hash for a memory fact."""
    normalized = fact_text.strip().lower()
    people_str = ",".join(sorted(p.lower() for p in (people or [])))
    content = f"{normalized}|{people_str}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _texts_match(existing: str, new: str) -> bool:
    """Check if two fact texts are similar enough to be NOOP."""
    a = existing.strip().lower()
    b = new.strip().lower()
    # Exact match or one is a prefix of the other
    return a == b or a.startswith(b) or b.startswith(a)


def _parse_date(
    value: str | None, default: datetime | None
) -> datetime | None:
    """Parse an ISO date string to a timezone-aware datetime."""
    if not value:
        return default

    try:
        # Try full datetime first
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        pass

    try:
        # Try date-only
        d = date.fromisoformat(value)
        return datetime.combine(d, datetime.min.time()).replace(
            tzinfo=timezone.utc
        )
    except (ValueError, TypeError):
        return default
