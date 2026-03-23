"""Google Calendar connector -- incremental sync via syncToken."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.models.enums import IntegrationProvider
from app.models.sync_state import SyncState
from app.services.connectors.base import SyncResult
from app.services.connectors.google_base import GoogleBaseConnector

logger = logging.getLogger(__name__)


class GoogleCalendarConnector(GoogleBaseConnector):
    """Connector for Google Calendar API with incremental sync."""

    provider = IntegrationProvider.GOOGLE_CALENDAR
    scopes = ["https://www.googleapis.com/auth/calendar.readonly"]

    async def sync(self, sync_state: SyncState | None) -> SyncResult:
        """Fetch calendar events using incremental sync.

        Uses syncToken for incremental updates. Falls back to full
        sync (next 7 days) if no syncToken exists.
        """
        result = SyncResult()

        try:
            creds = await self._ensure_credentials()
            if creds is None:
                result.errors.append("Authentication failed")
                return result

            service = build("calendar", "v3", credentials=creds)
            events_api = service.events()

            if sync_state and sync_state.cursor_value:
                try:
                    response = events_api.list(
                        calendarId="primary",
                        syncToken=sync_state.cursor_value,
                    ).execute()
                except HttpError as e:
                    if e.resp.status == 410:
                        logger.info("syncToken expired, doing full sync")
                        response = self._full_sync(events_api)
                    else:
                        raise
            else:
                response = self._full_sync(events_api)

            self._collect_events(response, result)

            # Handle pagination (only pageToken, never syncToken)
            while response.get("nextPageToken"):
                response = events_api.list(
                    calendarId="primary",
                    pageToken=response["nextPageToken"],
                ).execute()
                self._collect_events(response, result)

            result.documents_fetched = len(result.raw_items)
            self._mark_healthy()

        except Exception as e:
            logger.error("Google Calendar sync failed: %s", e)
            self._mark_error(str(e))
            result.errors.append(str(e))

        return result

    @staticmethod
    def _collect_events(response: dict, result: SyncResult) -> None:
        """Parse events from a Calendar API response into result."""
        for event in response.get("items", []):
            if event.get("status") == "cancelled":
                result.raw_items.append({
                    "external_id": event["id"],
                    "cancelled": True,
                })
                continue

            result.raw_items.append(_parse_event(event))

        # Always update cursor to the latest syncToken
        sync_token = response.get("nextSyncToken")
        if sync_token:
            result.new_cursor = sync_token

    @staticmethod
    def _full_sync(events_api) -> dict:
        """Full sync: fetch events for next 7 days."""
        now = datetime.now(timezone.utc)
        return events_api.list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=(now + timedelta(days=7)).isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=250,
        ).execute()


def _parse_event(event: dict) -> dict[str, Any]:
    """Convert a Google Calendar event to a normalized dict."""
    start = event.get("start", {})
    end = event.get("end", {})

    return {
        "external_id": event["id"],
        "title": event.get("summary", "(No title)"),
        "description": event.get("description"),
        "start_time": start.get("dateTime") or start.get("date"),
        "end_time": end.get("dateTime") or end.get("date"),
        "is_all_day": "date" in start and "dateTime" not in start,
        "location": event.get("location"),
        "attendees": [
            {
                "email": a.get("email"),
                "name": a.get("displayName"),
                "response": a.get("responseStatus"),
            }
            for a in event.get("attendees", [])
        ],
        "cancelled": False,
    }
