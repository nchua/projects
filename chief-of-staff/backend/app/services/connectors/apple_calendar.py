"""Apple Calendar connector — reads events via AppleScript.

Uses Calendar.app's AppleScript interface to fetch events.
No OAuth needed — macOS handles permissions natively.
"""

import logging
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Any

from app.models.enums import IntegrationProvider
from app.models.sync_state import SyncState
from app.services.connectors.base import BaseConnector, SyncResult

logger = logging.getLogger(__name__)

# AppleScript to list calendar names (used for auth check + selection UI)
_LIST_CALENDARS_SCRIPT = """
tell application "Calendar"
    set output to ""
    repeat with c in calendars
        set output to output & name of c & (ASCII character 10)
    end repeat
    return output
end tell
"""

# AppleScript to fetch events from specific calendars within a date range.
# Outputs tab-delimited lines: uid\ttitle\tstart_iso\tend_iso\tcalendar\tlocation\tnotes
# All parsing/escaping happens in Python — AppleScript just dumps raw text.
_EVENTS_SCRIPT_TEMPLATE = """
on sanitize(txt)
    -- Replace tabs and newlines with spaces so they don't break TSV format
    set oldTIDs to AppleScript's text item delimiters
    set AppleScript's text item delimiters to tab
    set parts to text items of txt
    set AppleScript's text item delimiters to " "
    set txt to parts as text
    set AppleScript's text item delimiters to (ASCII character 10)
    set parts to text items of txt
    set AppleScript's text item delimiters to " "
    set txt to parts as text
    set AppleScript's text item delimiters to (ASCII character 13)
    set parts to text items of txt
    set AppleScript's text item delimiters to " "
    set txt to parts as text
    set AppleScript's text item delimiters to oldTIDs
    return txt
end sanitize

tell application "Calendar"
    set startDate to (current date) - ({days_back} * days)
    set endDate to (current date) + ({days_forward} * days)
    set output to ""
    set targetCalNames to {{{calendar_list}}}

    repeat with cal in calendars
        set calName to name of cal
        if targetCalNames contains calName then
            set calNameSafe to my sanitize(calName)
            set calEvents to (every event of cal whose start date >= startDate and start date <= endDate)
            repeat with evt in calEvents
                set evtId to uid of evt
                set evtTitle to my sanitize(summary of evt)
                set evtStart to (start date of evt) as <<class isot>> as string
                set evtEnd to (end date of evt) as <<class isot>> as string
                set evtNotes to description of evt
                set evtLoc to location of evt
                if evtNotes is missing value then set evtNotes to ""
                if evtLoc is missing value then set evtLoc to ""
                set evtNotes to my sanitize(evtNotes)
                set evtLoc to my sanitize(evtLoc)

                set output to output & evtId & tab & evtTitle & tab & evtStart & tab & evtEnd & tab & calNameSafe & tab & evtLoc & tab & evtNotes & (ASCII character 10)
            end repeat
        end if
    end repeat

    return output
end tell
"""


def list_calendars() -> list[str]:
    """Return the names of all calendars visible in Calendar.app."""
    result = subprocess.run(
        ["osascript", "-e", _LIST_CALENDARS_SCRIPT],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Calendar access failed: {result.stderr.strip()}")

    names = [n.strip() for n in result.stdout.strip().split("\n") if n.strip()]
    return names


class AppleCalendarConnector(BaseConnector):
    """Connector for macOS Calendar.app via AppleScript."""

    provider = IntegrationProvider.APPLE_CALENDAR

    async def authenticate(self) -> bool:
        """Verify Calendar.app is accessible and we have permission."""
        try:
            list_calendars()
            self._mark_healthy()
            return True

        except subprocess.TimeoutExpired:
            self._mark_error("Calendar.app timed out — is it responding?")
            return False
        except Exception as e:
            error = str(e)
            if "not allowed" in error.lower() or "permission" in error.lower():
                self._mark_error(
                    "Calendar permission denied. Grant access in "
                    "System Settings > Privacy & Security > Calendars"
                )
            else:
                self._mark_error(f"Calendar access failed: {error}")
            return False

    async def sync(self, sync_state: SyncState | None) -> SyncResult:
        """Fetch calendar events using AppleScript.

        Uses date range as cursor — fetches events from the last cursor
        date (or 7 days ago) through 7 days from now.
        Only syncs calendars listed in integration.scopes.
        """
        result = SyncResult()

        # Get selected calendars from scopes (comma-separated names)
        selected = _parse_selected_calendars(self.integration.scopes)
        if not selected:
            result.errors.append(
                "No calendars selected. Disconnect and reconnect to choose calendars."
            )
            self._mark_error("No calendars selected")
            return result

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

            events = _fetch_events(start, end, selected)

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

        except subprocess.TimeoutExpired:
            msg = "AppleScript timed out — try selecting fewer calendars"
            logger.error("Apple Calendar sync timeout")
            self._mark_error(msg)
            result.errors.append(msg)
        except Exception as e:
            logger.error("Apple Calendar sync failed: %s", e)
            self._mark_error(str(e))
            result.errors.append(str(e))

        return result


def _parse_selected_calendars(scopes: str | None) -> list[str]:
    """Parse comma-separated calendar names from the scopes field.

    Returns empty list if scopes is None, empty, or the legacy placeholder.
    """
    if not scopes or scopes == "local_events":
        return []
    return [s.strip() for s in scopes.split(",") if s.strip()]


def _fetch_events(
    start: datetime,
    end: datetime,
    calendars: list[str],
) -> list[dict[str, Any]]:
    """Run AppleScript to fetch events from selected calendars.

    Returns list of event dicts parsed from tab-delimited AppleScript output.
    """
    now = datetime.now(timezone.utc)
    days_back = max(0, (now - start).days)
    days_forward = max(1, (end - now).days)

    # Build AppleScript list literal: {"Calendar 1", "Calendar 2"}
    escaped = [name.replace('"', '\\"') for name in calendars]
    calendar_list = ", ".join(f'"{name}"' for name in escaped)

    script = _EVENTS_SCRIPT_TEMPLATE.format(
        days_back=days_back,
        days_forward=days_forward,
        calendar_list=calendar_list,
    )

    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        raise RuntimeError(f"AppleScript error: {result.stderr.strip()}")

    output = result.stdout.strip()
    if not output:
        return []

    events: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for line in output.split("\n"):
        parts = line.split("\t")
        if len(parts) < 5:
            logger.warning("Skipping malformed calendar line: %s", line[:100])
            continue
        event_id = parts[0]
        if event_id in seen_ids:
            continue
        seen_ids.add(event_id)
        events.append({
            "id": event_id,
            "title": parts[1],
            "start": parts[2],
            "end": parts[3],
            "calendar": parts[4],
            "location": parts[5] if len(parts) > 5 else "",
            "notes": parts[6] if len(parts) > 6 else "",
        })

    return events
