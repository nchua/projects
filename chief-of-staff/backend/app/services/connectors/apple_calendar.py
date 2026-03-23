"""Apple Calendar connector — reads events via AppleScript.

Uses Calendar.app's AppleScript interface to fetch events.
No OAuth needed — macOS handles permissions natively.
"""

import json
import logging
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Any

from app.models.enums import IntegrationProvider
from app.models.sync_state import SyncState
from app.services.connectors.base import BaseConnector, SyncResult

logger = logging.getLogger(__name__)

# AppleScript to list calendar names (used for auth check)
_AUTH_CHECK_SCRIPT = """
tell application "Calendar"
    set calNames to {}
    repeat with c in calendars
        set end of calNames to name of c
    end repeat
    return calNames
end tell
"""

# AppleScript to fetch events from all calendars within a date range.
# Returns JSON-formatted list of events.
_EVENTS_SCRIPT_TEMPLATE = """
use AppleScript version "2.4"
use scripting additions
use framework "Foundation"

on formatDate(d)
    set formatter to current application's NSDateFormatter's alloc()'s init()
    formatter's setDateFormat:"yyyy-MM-dd'T'HH:mm:ssZZZZZ"
    set nsDate to current application's NSDate's dateWithTimeIntervalSince1970:(d's time to real)
    return (formatter's stringFromDate:nsDate) as text
end formatDate

tell application "Calendar"
    set startDate to date "{start_date}"
    set endDate to date "{end_date}"
    set allEvents to {{}}

    repeat with cal in calendars
        set calName to name of cal
        set calEvents to (every event of cal whose start date >= startDate and start date <= endDate)
        repeat with evt in calEvents
            set evtId to uid of evt
            set evtTitle to summary of evt
            set evtStart to start date of evt
            set evtEnd to end date of evt
            set evtNotes to description of evt
            set evtLoc to location of evt

            if evtNotes is missing value then set evtNotes to ""
            if evtLoc is missing value then set evtLoc to ""

            set evtRecord to "{{" & ¬
                "\\"id\\": \\"" & evtId & "\\", " & ¬
                "\\"title\\": \\"" & evtTitle & "\\", " & ¬
                "\\"start\\": \\"" & (evtStart as «class isot» as string) & "\\", " & ¬
                "\\"end\\": \\"" & (evtEnd as «class isot» as string) & "\\", " & ¬
                "\\"calendar\\": \\"" & calName & "\\", " & ¬
                "\\"location\\": \\"" & evtLoc & "\\", " & ¬
                "\\"notes\\": \\"" & evtNotes & "\\"" & ¬
                "}}"
            set end of allEvents to evtRecord
        end repeat
    end repeat

    set AppleScript's text item delimiters to ", "
    return "[" & (allEvents as text) & "]"
end tell
"""


class AppleCalendarConnector(BaseConnector):
    """Connector for macOS Calendar.app via AppleScript."""

    provider = IntegrationProvider.APPLE_CALENDAR

    async def authenticate(self) -> bool:
        """Verify Calendar.app is accessible and we have permission."""
        try:
            result = subprocess.run(
                ["osascript", "-e", _AUTH_CHECK_SCRIPT],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                error = result.stderr.strip()
                if "not allowed" in error.lower() or "permission" in error.lower():
                    self._mark_error(
                        "Calendar permission denied. Grant access in "
                        "System Settings > Privacy & Security > Calendars"
                    )
                else:
                    self._mark_error(f"Calendar access failed: {error}")
                return False

            self._mark_healthy()
            return True

        except subprocess.TimeoutExpired:
            self._mark_error("Calendar.app timed out — is it responding?")
            return False
        except Exception as e:
            logger.error("Apple Calendar auth failed: %s", e)
            self._mark_error(str(e))
            return False

    async def sync(self, sync_state: SyncState | None) -> SyncResult:
        """Fetch calendar events using AppleScript.

        Uses date range as cursor — fetches events from the last cursor
        date (or 7 days ago) through 7 days from now.
        """
        result = SyncResult()

        try:
            # Determine date range
            now = datetime.now(timezone.utc)
            if sync_state and sync_state.cursor_value:
                try:
                    start = datetime.fromisoformat(sync_state.cursor_value)
                except ValueError:
                    start = now - timedelta(days=7)
            else:
                start = now - timedelta(days=7)

            end = now + timedelta(days=7)

            events = _fetch_events(start, end)

            for event in events:
                result.raw_items.append({
                    "source_id": f"apple_calendar:{event.get('id', '')}",
                    "source_url": "",
                    "title": event.get("title", "(No title)"),
                    "date": event.get("start"),
                    "end_date": event.get("end"),
                    "calendar": event.get("calendar", ""),
                    "location": event.get("location", ""),
                    "attendees": [],
                    "notes": event.get("notes", ""),
                    "body": event.get("notes", ""),
                })

            result.documents_fetched = len(result.raw_items)
            result.new_cursor = now.isoformat()
            self._mark_healthy()

        except Exception as e:
            logger.error("Apple Calendar sync failed: %s", e)
            self._mark_error(str(e))
            result.errors.append(str(e))

        return result


def _fetch_events(
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    """Run AppleScript to fetch events in the given date range."""
    # Format dates as AppleScript expects: "Monday, March 23, 2026 12:00:00 AM"
    start_str = start.strftime("%A, %B %d, %Y %I:%M:%S %p")
    end_str = end.strftime("%A, %B %d, %Y %I:%M:%S %p")

    script = _EVENTS_SCRIPT_TEMPLATE.format(
        start_date=start_str,
        end_date=end_str,
    )

    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        raise RuntimeError(f"AppleScript error: {result.stderr.strip()}")

    output = result.stdout.strip()
    if not output or output == "[]":
        return []

    try:
        return json.loads(output)
    except json.JSONDecodeError:
        # AppleScript JSON can be messy — try to salvage
        logger.warning("Failed to parse AppleScript output as JSON: %s", output[:200])
        return []
