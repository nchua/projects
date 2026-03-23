"""Slack connector — Bot API with cursor-based incremental sync."""

import logging
from datetime import datetime, timezone

from app.models.enums import IntegrationProvider
from app.models.sync_state import SyncState
from app.services.connectors.base import BaseConnector, SyncResult

logger = logging.getLogger(__name__)

SLACK_API_BASE = "https://slack.com/api"


class SlackConnector(BaseConnector):
    """Connector for Slack Bot API — messages and mentions."""

    provider = IntegrationProvider.SLACK

    async def authenticate(self) -> bool:
        """Validate the Slack bot token via auth.test."""
        try:
            token = self._decrypt_auth_token()
            client = await self.get_http_client()
            response = await client.post(
                f"{SLACK_API_BASE}/auth.test",
                headers=_auth_headers(token),
            )

            data = response.json()
            if data.get("ok"):
                self._mark_healthy()
                return True

            self._mark_error(f"Slack auth.test failed: {data.get('error')}")
            return False
        except Exception as e:
            logger.error("Slack auth failed: %s", e)
            self._mark_error(str(e))
            return False

    async def sync(self, sync_state: SyncState | None) -> SyncResult:
        """Fetch recent messages from channels where user is mentioned or DMed.

        Uses conversations.list to get channels, then conversations.history
        with `oldest` timestamp for incremental sync.
        """
        result = SyncResult()

        try:
            token = self._decrypt_auth_token()
            client = await self.get_http_client()
            headers = _auth_headers(token)

            # Get the bot's own user ID for filtering mentions
            auth_resp = await client.post(
                f"{SLACK_API_BASE}/auth.test",
                headers=headers,
            )
            auth_data = auth_resp.json()
            if not auth_data.get("ok"):
                self._mark_error(f"auth.test failed: {auth_data.get('error')}")
                result.errors.append(auth_data.get("error", "auth.test failed"))
                return result
            bot_user_id = auth_data.get("user_id", "")

            # Determine oldest timestamp for incremental sync
            oldest = "0"
            if sync_state and sync_state.cursor_value:
                oldest = sync_state.cursor_value

            # Fetch channels the bot is in (public + private + DMs)
            channels = await _list_channels(client, headers)

            # Fetch history from each channel
            for channel in channels:
                channel_id = channel.get("id", "")
                channel_name = channel.get("name", channel_id)
                is_im = channel.get("is_im", False)

                messages = await _fetch_channel_history(
                    client, headers, channel_id, oldest
                )

                for msg in messages:
                    text = msg.get("text", "")
                    msg_user = msg.get("user", "")
                    ts = msg.get("ts", "")

                    # Include if: it's a DM, or user is mentioned
                    is_mention = f"<@{bot_user_id}>" in text
                    if not is_im and not is_mention:
                        # Also check if bot_user_id is directly mentioned
                        # in any form — skip messages that don't involve us
                        continue

                    # Build permalink (best-effort)
                    team_id = auth_data.get("team_id", "")
                    permalink = (
                        f"https://app.slack.com/archives/{channel_id}/p{ts.replace('.', '')}"
                        if ts
                        else ""
                    )

                    result.raw_items.append({
                        "source_id": f"slack:{channel_id}:{ts}",
                        "source_url": permalink,
                        "body": text,
                        "channel": channel_name,
                        "channel_id": channel_id,
                        "sender": msg_user,
                        "timestamp": ts,
                        "is_dm": is_im,
                    })

            result.documents_fetched = len(result.raw_items)

            # New cursor: current time as Unix timestamp string
            result.new_cursor = str(datetime.now(timezone.utc).timestamp())
            self._mark_healthy()

            # Track rate limits from Slack headers
            # Slack uses Retry-After rather than X-RateLimit headers,
            # so we don't update rate limits here.

        except Exception as e:
            logger.error("Slack sync failed: %s", e)
            self._mark_error(str(e))
            result.errors.append(str(e))

        return result


async def _list_channels(
    client: "httpx.AsyncClient",
    headers: dict[str, str],
) -> list[dict]:
    """List all conversations the bot is a member of."""
    channels: list[dict] = []
    cursor = None

    for _ in range(10):  # Max 10 pages
        params: dict[str, str] = {
            "types": "public_channel,private_channel,im,mpim",
            "exclude_archived": "true",
            "limit": "200",
        }
        if cursor:
            params["cursor"] = cursor

        response = await client.get(
            f"{SLACK_API_BASE}/conversations.list",
            headers=headers,
            params=params,
        )
        data = response.json()
        if not data.get("ok"):
            logger.warning("conversations.list failed: %s", data.get("error"))
            break

        channels.extend(data.get("channels", []))

        cursor = data.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break

    return channels


async def _fetch_channel_history(
    client: "httpx.AsyncClient",
    headers: dict[str, str],
    channel_id: str,
    oldest: str,
) -> list[dict]:
    """Fetch message history from a channel since `oldest` timestamp."""
    messages: list[dict] = []
    cursor = None

    for _ in range(5):  # Max 5 pages per channel
        params: dict[str, str] = {
            "channel": channel_id,
            "oldest": oldest,
            "limit": "100",
        }
        if cursor:
            params["cursor"] = cursor

        response = await client.get(
            f"{SLACK_API_BASE}/conversations.history",
            headers=headers,
            params=params,
        )
        data = response.json()
        if not data.get("ok"):
            error = data.get("error", "")
            # not_in_channel or channel_not_found are expected for some channels
            if error not in ("not_in_channel", "channel_not_found"):
                logger.warning(
                    "conversations.history failed for %s: %s",
                    channel_id, error,
                )
            break

        messages.extend(data.get("messages", []))

        if not data.get("has_more", False):
            break
        cursor = data.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break

    return messages


def _auth_headers(token: str) -> dict[str, str]:
    """Build Slack API auth headers."""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
