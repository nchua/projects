"""Gmail connector -- incremental sync via historyId with data minimization."""

import base64
import hashlib
import logging
import re
from html.parser import HTMLParser

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.models.enums import IntegrationProvider
from app.models.sync_state import SyncState
from app.services.connectors.base import SyncResult
from app.services.connectors.google_base import GoogleBaseConnector

logger = logging.getLogger(__name__)

# Max chars to send to the AI extraction pipeline
MAX_BODY_CHARS = 8000
MIN_BODY_CHARS = 50


class _HTMLTextExtractor(HTMLParser):
    """Strips HTML tags and extracts plain text."""

    BLOCK_TAGS = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr"}
    SKIP_TAGS = {"script", "style"}

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag.lower() in self.SKIP_TAGS:
            self._skip = True
        if tag.lower() in self.BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.SKIP_TAGS:
            self._skip = False
        if tag.lower() in self.BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts).strip()


def html_to_text(html: str) -> str:
    """Convert HTML to plain text."""
    parser = _HTMLTextExtractor()
    parser.feed(html)
    return parser.get_text()


def strip_email_noise(text: str) -> str:
    """Strip signatures, quoted replies, marketing footers.

    Data minimization step -- reduce content before AI processing.
    """
    lines = text.split("\n")
    cleaned: list[str] = []

    for line in lines:
        stripped = line.strip()

        # Quoted reply markers
        if stripped.startswith(">"):
            continue
        if re.match(r"^On .+ wrote:$", stripped):
            break
        if re.match(r"^-{3,}\s*(Original Message|Forwarded)", stripped, re.IGNORECASE):
            break

        # Common signature markers
        if stripped in ("--", "---", "Sent from my iPhone", "Sent from my iPad"):
            break
        if re.match(r"^Get Outlook for", stripped, re.IGNORECASE):
            break

        # Marketing/unsubscribe footers
        if re.search(r"unsubscribe|opt.out|email preferences", stripped, re.IGNORECASE):
            continue
        if re.search(r"view.*(in|this).*(browser|email)", stripped, re.IGNORECASE):
            continue

        cleaned.append(line)

    return "\n".join(cleaned).strip()


def truncate_for_api(text: str, max_chars: int = MAX_BODY_CHARS) -> str:
    """Truncate text to max length with marker."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n[truncated]"


def hash_content(text: str) -> str:
    """SHA-256 hash for dedup checking."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class GmailConnector(GoogleBaseConnector):
    """Connector for Gmail API with history-based incremental sync."""

    provider = IntegrationProvider.GMAIL
    scopes = ["https://www.googleapis.com/auth/gmail.readonly"]

    async def sync(self, sync_state: SyncState | None) -> SyncResult:
        """Fetch new messages via history-based incremental sync.

        Uses historyId to fetch only messages that arrived since last sync.
        Falls back to listing recent INBOX messages on first sync.
        """
        result = SyncResult()

        try:
            creds = await self._ensure_credentials()
            if creds is None:
                result.errors.append("Authentication failed")
                return result

            service = build("gmail", "v1", credentials=creds)

            if sync_state and sync_state.cursor_value:
                message_ids = await self._fetch_history(
                    service, sync_state.cursor_value, result
                )
            else:
                message_ids, new_history_id = await self._fetch_recent(service)
                if new_history_id:
                    result.new_cursor = new_history_id

            for msg_id in message_ids:
                msg_data = self._fetch_message(service, msg_id)
                if msg_data:
                    result.raw_items.append(msg_data)

            result.documents_fetched = len(result.raw_items)
            self._mark_healthy()

        except Exception as e:
            logger.error("Gmail sync failed: %s", e)
            self._mark_error(str(e))
            result.errors.append(str(e))

        return result

    async def _fetch_history(
        self, service, history_id: str, result: SyncResult
    ) -> list[str]:
        """Fetch message IDs added since the given historyId."""
        message_ids: list[str] = []

        try:
            response = (
                service.users()
                .history()
                .list(
                    userId="me",
                    startHistoryId=history_id,
                    historyTypes=["messageAdded"],
                    labelId="INBOX",
                    maxResults=50,
                )
                .execute()
            )

            for record in response.get("history", []):
                for added in record.get("messagesAdded", []):
                    msg = added.get("message", {})
                    if msg.get("id"):
                        message_ids.append(msg["id"])

            result.new_cursor = str(response.get("historyId", history_id))

        except HttpError as e:
            if e.resp.status == 404:
                logger.info("historyId expired, fetching recent messages")
                message_ids, new_history_id = await self._fetch_recent(service)
                if new_history_id:
                    result.new_cursor = new_history_id
            else:
                raise

        return message_ids

    async def _fetch_recent(
        self, service
    ) -> tuple[list[str], str | None]:
        """Fetch the 20 most recent inbox messages for initial sync."""
        response = (
            service.users()
            .messages()
            .list(userId="me", labelIds=["INBOX"], maxResults=20)
            .execute()
        )

        message_ids = [m["id"] for m in response.get("messages", [])]

        if message_ids:
            first_msg = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=message_ids[0],
                    format="metadata",
                    metadataHeaders=["Message-ID"],
                )
                .execute()
            )
            return message_ids, str(first_msg.get("historyId", ""))

        return message_ids, None

    def _fetch_message(self, service, msg_id: str) -> dict | None:
        """Fetch and parse a single message.

        Returns a dict with headers and preprocessed body text,
        or None if the message can't be parsed.
        """
        try:
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_id, format="full")
                .execute()
            )

            headers = {
                h["name"]: h["value"]
                for h in msg.get("payload", {}).get("headers", [])
            }

            body = self._extract_body(msg.get("payload", {}))
            if not body or len(body) < MIN_BODY_CHARS:
                return None

            body = strip_email_noise(body)
            if len(body) < MIN_BODY_CHARS:
                return None

            body = truncate_for_api(body)

            return {
                "source_id": msg_id,
                "source_url": f"https://mail.google.com/mail/u/0/#inbox/{msg_id}",
                "subject": headers.get("Subject", "(No subject)"),
                "sender": headers.get("From", ""),
                "to": headers.get("To", ""),
                "date": headers.get("Date", ""),
                "body": body,
                "dedup_hash": hash_content(f"{msg_id}:{body[:500]}"),
            }
        except Exception as e:
            logger.warning("Failed to fetch message %s: %s", msg_id, e)
            return None

    def _extract_body(self, payload: dict) -> str:
        """Extract plain text body from a Gmail message payload.

        Handles multipart MIME, preferring text/plain over HTML.
        """
        mime_type = payload.get("mimeType", "")
        body_data = payload.get("body", {}).get("data")

        if mime_type == "text/plain" and body_data:
            return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")

        if mime_type == "text/html" and body_data:
            html = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
            return html_to_text(html)

        # Multipart -- recurse into parts
        parts = payload.get("parts", [])
        if parts:
            # Prefer text/plain
            for part in parts:
                if part.get("mimeType") == "text/plain":
                    data = part.get("body", {}).get("data")
                    if data:
                        return base64.urlsafe_b64decode(data).decode(
                            "utf-8", errors="replace"
                        )

            # Fall back to text/html
            for part in parts:
                if part.get("mimeType") == "text/html":
                    data = part.get("body", {}).get("data")
                    if data:
                        html = base64.urlsafe_b64decode(data).decode(
                            "utf-8", errors="replace"
                        )
                        return html_to_text(html)

            # Recurse into nested multipart
            for part in parts:
                text = self._extract_body(part)
                if text:
                    return text

        return ""
