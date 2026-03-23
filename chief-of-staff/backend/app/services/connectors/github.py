"""GitHub connector — notifications API with since-based sync."""

import logging
from datetime import datetime, timezone

from app.models.enums import IntegrationProvider
from app.models.sync_state import SyncState
from app.services.connectors.base import BaseConnector, SyncResult

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"


class GitHubConnector(BaseConnector):
    """Connector for GitHub REST API notifications."""

    provider = IntegrationProvider.GITHUB

    async def authenticate(self) -> bool:
        """Validate the GitHub token by fetching the authenticated user."""
        try:
            token = self._decrypt_auth_token()
            client = await self.get_http_client()
            response = await client.get(
                f"{GITHUB_API_BASE}/user",
                headers=self._auth_headers(token),
            )
            if response.status_code == 200:
                self._mark_healthy()
                return True

            self._mark_error(f"GitHub auth returned {response.status_code}")
            return False
        except Exception as e:
            logger.error("GitHub auth failed: %s", e)
            self._mark_error(str(e))
            return False

    async def sync(self, sync_state: SyncState | None) -> SyncResult:
        """Fetch notifications since last sync.

        GitHub tokens are long-lived — no refresh needed.
        Uses the `since` parameter for incremental sync.
        """
        result = SyncResult()

        try:
            token = self._decrypt_auth_token()
            client = await self.get_http_client()
            headers = self._auth_headers(token)

            # Build params
            params: dict[str, str] = {"all": "true", "per_page": "50"}
            if sync_state and sync_state.cursor_value:
                params["since"] = sync_state.cursor_value

            response = await client.get(
                f"{GITHUB_API_BASE}/notifications",
                headers=headers,
                params=params,
            )

            if response.status_code != 200:
                self._mark_error(
                    f"GitHub notifications returned {response.status_code}"
                )
                result.errors.append(f"HTTP {response.status_code}")
                return result

            # Track rate limits
            self._update_rate_limits(
                remaining=_parse_int(response.headers.get("X-RateLimit-Remaining")),
                reset_at=_parse_reset(response.headers.get("X-RateLimit-Reset")),
            )

            notifications = response.json()

            for notif in notifications:
                subject = notif.get("subject", {})
                notif_type = subject.get("type", "")
                reason = notif.get("reason", "")

                # Map to action-item-relevant categories
                item = {
                    "source_id": notif["id"],
                    "source_url": self._build_web_url(subject),
                    "title": subject.get("title", "(No title)"),
                    "notification_type": notif_type,
                    "reason": reason,
                    "repository": notif.get("repository", {}).get("full_name", ""),
                    "updated_at": notif.get("updated_at", ""),
                    "unread": notif.get("unread", False),
                }

                # Enrich with extra context based on type
                if notif_type == "PullRequest" and reason in (
                    "review_requested",
                    "assign",
                ):
                    item["action_type"] = "pr_review_requested"
                elif notif_type == "Issue" and reason == "assign":
                    item["action_type"] = "issue_assigned"
                elif notif_type == "CheckSuite" or (
                    notif_type == "PullRequest" and reason == "ci_activity"
                ):
                    item["action_type"] = "ci_failure"
                elif reason == "mention" and notif_type in (
                    "PullRequest",
                    "Issue",
                ):
                    item["action_type"] = "mentioned"
                else:
                    item["action_type"] = "other"

                result.raw_items.append(item)

            result.documents_fetched = len(result.raw_items)

            # New cursor: current time in ISO format
            result.new_cursor = datetime.now(timezone.utc).isoformat()
            self._mark_healthy()

        except Exception as e:
            logger.error("GitHub sync failed: %s", e)
            self._mark_error(str(e))
            result.errors.append(str(e))

        return result

    @staticmethod
    def _auth_headers(token: str) -> dict[str, str]:
        """Build GitHub API auth headers."""
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    @staticmethod
    def _build_web_url(subject: dict) -> str:
        """Convert API URL to web URL.

        GitHub notification subject URLs are API URLs like:
        https://api.github.com/repos/owner/repo/pulls/123
        Convert to: https://github.com/owner/repo/pull/123
        """
        api_url = subject.get("url", "")
        if not api_url:
            return ""

        web_url = api_url.replace("https://api.github.com/repos/", "https://github.com/")
        web_url = web_url.replace("/pulls/", "/pull/")
        return web_url


def _parse_int(value: str | None) -> int | None:
    """Parse an integer from a header value."""
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_reset(value: str | None) -> datetime | None:
    """Parse a Unix timestamp from X-RateLimit-Reset header."""
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (ValueError, OSError):
        return None
