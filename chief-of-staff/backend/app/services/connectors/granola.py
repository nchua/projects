"""Granola connector — reads meeting notes from local JSON cache.

Granola stores meeting data in a local JSON file at:
~/Library/Application Support/Granola/cache-v6.json

Structure: {"cache": {"state": {"documents": {}, "transcripts": {}, "meetingsMetadata": {}}}}

No API calls needed — this reads directly from the filesystem.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from app.models.enums import IntegrationProvider
from app.models.sync_state import SyncState
from app.services.connectors.base import BaseConnector, SyncResult

logger = logging.getLogger(__name__)


class GranolaConnector(BaseConnector):
    """Connector for Granola local meeting notes cache."""

    provider = IntegrationProvider.GRANOLA

    async def authenticate(self) -> bool:
        """Verify the cache file exists and is readable."""
        try:
            cache_path = self._decrypt_auth_token()
            if not os.path.isfile(cache_path):
                self._mark_error(f"Cache file not found: {cache_path}")
                return False

            # Verify it's valid JSON
            with open(cache_path, "r") as f:
                data = json.load(f)

            if "cache" not in data:
                self._mark_error("Invalid Granola cache format: missing 'cache' key")
                return False

            self._mark_healthy()
            return True
        except json.JSONDecodeError as e:
            self._mark_error(f"Invalid JSON in cache file: {e}")
            return False
        except Exception as e:
            logger.error("Granola auth failed: %s", e)
            self._mark_error(str(e))
            return False

    async def sync(self, sync_state: SyncState | None) -> SyncResult:
        """Read meeting notes from the local Granola cache.

        Uses meeting timestamps as cursor — only returns meetings
        newer than the last sync cursor.
        """
        result = SyncResult()

        try:
            cache_path = self._decrypt_auth_token()

            with open(cache_path, "r") as f:
                data = json.load(f)

            state = data.get("cache", {}).get("state", {})
            documents = state.get("documents", {})
            meetings_metadata = state.get("meetingsMetadata", {})

            # Determine cutoff timestamp for incremental sync
            cutoff_ts = 0.0
            if sync_state and sync_state.cursor_value:
                try:
                    cutoff_ts = float(sync_state.cursor_value)
                except ValueError:
                    cutoff_ts = 0.0

            latest_ts = cutoff_ts

            for doc_id, doc in documents.items():
                meeting_ts = _parse_meeting_timestamp(doc, meetings_metadata.get(doc_id, {}))
                if meeting_ts <= cutoff_ts:
                    continue

                latest_ts = max(latest_ts, meeting_ts)

                # Extract meeting data
                metadata = meetings_metadata.get(doc_id, {})
                title = doc.get("title") or metadata.get("title") or "(Untitled meeting)"
                notes = doc.get("content") or doc.get("notes") or ""
                attendees = _extract_attendees(metadata)
                meeting_date = _ts_to_iso(meeting_ts) if meeting_ts > 0 else None

                result.raw_items.append({
                    "source_id": f"granola:{doc_id}",
                    "source_url": "",
                    "title": title,
                    "date": meeting_date,
                    "attendees": attendees,
                    "notes": notes,
                    "body": notes,
                })

            result.documents_fetched = len(result.raw_items)

            # Update cursor to latest meeting timestamp
            if latest_ts > cutoff_ts:
                result.new_cursor = str(latest_ts)
            else:
                result.new_cursor = str(datetime.now(timezone.utc).timestamp())

            self._mark_healthy()

        except json.JSONDecodeError as e:
            logger.error("Granola cache parse error: %s", e)
            self._mark_error(f"JSON parse error: {e}")
            result.errors.append(str(e))
        except Exception as e:
            logger.error("Granola sync failed: %s", e)
            self._mark_error(str(e))
            result.errors.append(str(e))

        return result


def _parse_meeting_timestamp(
    doc: dict[str, Any],
    metadata: dict[str, Any],
) -> float:
    """Extract a Unix timestamp from meeting data."""
    # Try common timestamp fields
    for field in ("created_at", "createdAt", "date", "start_time", "startTime"):
        val = doc.get(field) or metadata.get(field)
        if val is None:
            continue
        if isinstance(val, (int, float)):
            # If it looks like milliseconds, convert to seconds
            return val / 1000 if val > 1e12 else val
        if isinstance(val, str):
            try:
                dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                return dt.timestamp()
            except ValueError:
                continue
    return 0.0


def _extract_attendees(metadata: dict[str, Any]) -> list[str]:
    """Extract attendee names/emails from meeting metadata."""
    attendees = metadata.get("attendees") or metadata.get("participants") or []
    if isinstance(attendees, list):
        return [
            a.get("name") or a.get("email") or str(a)
            if isinstance(a, dict)
            else str(a)
            for a in attendees
        ]
    return []


def _ts_to_iso(ts: float) -> str:
    """Convert Unix timestamp to ISO 8601 string."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
