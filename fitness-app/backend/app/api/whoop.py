"""
WHOOP API endpoints (Phase 1 wearable HR).

  GET  /whoop/connect   -> returns the WHOOP OAuth authorize URL (auth required)
  GET  /whoop/callback  -> OAuth redirect target; exchanges code for tokens
  POST /whoop/sync      -> pull recent WHOOP workouts + backfill HR (auth required)
  GET  /whoop/status    -> connection status for the current user (auth required)

Credentials are read from env vars (WHOOP_CLIENT_ID / WHOOP_CLIENT_SECRET /
WHOOP_REDIRECT_URI). When unset, the connect/sync endpoints return 503 so the
rest of the app keeps working without WHOOP configured.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.utils import to_iso8601_utc
from app.models.user import User
from app.services import whoop_service
from app.services.whoop_service import (
    WhoopError,
    WhoopNotConfigured,
    WhoopNotConnected,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/connect")
async def whoop_connect(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the WHOOP authorize URL for the iOS client to open in a browser."""
    try:
        url = whoop_service.get_authorize_url(current_user.id)
    except WhoopNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        )
    return {"authorize_url": url}


@router.get("/callback", response_class=HTMLResponse)
async def whoop_callback(
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
    db: Session = Depends(get_db),
):
    """
    OAuth redirect target. WHOOP redirects the user's browser here with a
    `code` + the `state` we issued. We recover the user from the signed state
    (the browser doesn't carry the app's bearer token), exchange the code for
    tokens, and store the connection.
    """
    if error:
        return _callback_page("WHOOP connection failed", f"WHOOP returned an error: {error}", ok=False)

    user_id = whoop_service.verify_oauth_state(state)
    if not user_id:
        return _callback_page(
            "WHOOP connection failed",
            "Invalid or expired authorization state. Please start the connection again from the app.",
            ok=False,
        )
    if not code:
        return _callback_page(
            "WHOOP connection failed", "No authorization code was provided.", ok=False
        )

    try:
        whoop_service.exchange_code_for_token(db, user_id, code)
        db.commit()
    except WhoopNotConfigured as exc:
        return _callback_page("WHOOP not configured", str(exc), ok=False)
    except WhoopError as exc:
        db.rollback()
        logger.warning("WHOOP token exchange failed for user %s: %s", user_id, exc)
        return _callback_page(
            "WHOOP connection failed",
            "Could not complete the WHOOP connection. Please try again.",
            ok=False,
        )

    return _callback_page(
        "WHOOP connected",
        "Your WHOOP account is now connected. You can return to the app and sync your workouts.",
        ok=True,
    )


@router.post("/sync")
async def whoop_sync(
    days: int = Query(default=30, ge=1, le=180),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Pull recent WHOOP workouts and backfill matching sessions' HR summary.

    Also pulls recent recoveries + sleeps into daily_activity (ARISE v2.1) so
    Condition's inputs stay fresh. Recovery failures don't fail the whole sync
    — a pre-v2.1 connection without the read:recovery grant still syncs
    workouts until the user reconnects.
    """
    try:
        result = whoop_service.sync_recent_workouts(db, current_user.id, days=days)
        try:
            result["recovery"] = whoop_service.sync_recent_recovery(db, current_user.id)
        except WhoopError as exc:
            logger.warning(
                "WHOOP recovery sync failed for user %s: %s", current_user.id, exc
            )
            result["recovery"] = None
        db.commit()
    except WhoopNotConnected as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except WhoopNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        )
    except WhoopError as exc:
        db.rollback()
        logger.warning("WHOOP sync failed for user %s: %s", current_user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="WHOOP sync failed. Please try again later.",
        )
    return result


@router.get("/status")
async def whoop_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return whether the current user has a connected WHOOP account."""
    configured = whoop_service.is_configured()
    conn = whoop_service.get_connection(db, current_user.id)
    if conn is None:
        return {"connected": False, "configured": configured}
    return {
        "connected": True,
        "configured": configured,
        "whoop_user_id": conn.whoop_user_id,
        "scope": conn.scope,
        "expires_at": to_iso8601_utc(conn.expires_at),
        "last_synced_at": to_iso8601_utc(conn.last_synced_at),
    }


def _callback_page(title: str, message: str, ok: bool) -> HTMLResponse:
    """Minimal styled confirmation page shown after the OAuth redirect."""
    accent = "#00e5ff" if ok else "#ff5470"
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ARISE - {title}</title>
<style>
  body {{ background: #0a0a0f; color: #c8ccd4; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; line-height: 1.7; margin: 0; padding: 40px 20px; text-align: center; }}
  .card {{ max-width: 460px; margin: 60px auto; padding: 32px 24px; border: 1px solid #1a1a2e; border-radius: 16px; background: #11111a; }}
  h1 {{ color: {accent}; font-size: 20px; letter-spacing: 2px; text-transform: uppercase; }}
  p {{ font-size: 15px; color: #9a9eb0; }}
</style>
</head>
<body>
  <div class="card">
    <h1>{title}</h1>
    <p>{message}</p>
  </div>
</body>
</html>"""
    return HTMLResponse(content=html, status_code=200 if ok else 400)
