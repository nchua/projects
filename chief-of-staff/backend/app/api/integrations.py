"""Integration management and OAuth flow API endpoints."""

import logging
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.encryption import decrypt_token, encrypt_token
from app.models.enums import IntegrationProvider
from app.models.integration import Integration
from app.models.user import User
from app.schemas.integration import (
    IntegrationHealthResponse,
    IntegrationResponse,
    OAuthCallbackRequest,
)
from app.services.audit_log import log_audit

logger = logging.getLogger(__name__)

router = APIRouter()

# Google OAuth constants
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
]

# GitHub OAuth constants
GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"

GITHUB_SCOPES = ["notifications", "repo:status"]


@router.get("", response_model=list[IntegrationResponse])
def list_integrations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[IntegrationResponse]:
    """List all integrations for the current user.

    Tokens are never exposed in the response.
    """
    integrations = (
        db.query(Integration)
        .filter(Integration.user_id == current_user.id)
        .all()
    )
    return integrations


@router.get("/health", response_model=list[IntegrationHealthResponse])
def integration_health(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[IntegrationHealthResponse]:
    """Get a lightweight health overview of all integrations."""
    integrations = (
        db.query(Integration)
        .filter(
            Integration.user_id == current_user.id,
            Integration.is_active.is_(True),
        )
        .all()
    )
    return [
        IntegrationHealthResponse(
            provider=i.provider,
            status=i.status,
            last_synced_at=i.last_synced_at,
            is_active=i.is_active,
        )
        for i in integrations
    ]


# --- Google OAuth ---


@router.post("/google/authorize")
def google_authorize(
    redirect_uri: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Generate a Google OAuth authorization URL.

    The frontend redirects the user to this URL. After the user
    consents, Google redirects back to redirect_uri with a code.
    """
    settings = get_settings()
    if not settings.google_client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth not configured",
        )

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    return {"authorization_url": auth_url}


@router.post("/google/callback", response_model=IntegrationResponse)
def google_callback(
    callback: OAuthCallbackRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IntegrationResponse:
    """Exchange a Google OAuth authorization code for tokens.

    Creates or updates the Google integration (covering both
    Calendar and Gmail from a single OAuth consent).
    """
    settings = get_settings()

    response = httpx.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": callback.code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": callback.redirect_uri,
            "grant_type": "authorization_code",
        },
    )

    if response.status_code != 200:
        log_audit(
            db,
            "oauth_callback",
            user_id=current_user.id,
            success=False,
            error_details=f"Google token exchange failed: {response.text}",
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to exchange authorization code",
        )

    token_data = response.json()
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    scopes = token_data.get("scope", "")

    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No access token in response",
        )

    integration = _upsert_integration(
        db,
        user_id=current_user.id,
        provider=callback.provider.value,
        access_token=access_token,
        refresh_token=refresh_token,
        scopes=scopes,
    )

    log_audit(
        db,
        "oauth_callback",
        user_id=current_user.id,
        integration_id=integration.id,
        metadata={"provider": callback.provider.value},
    )

    db.commit()
    db.refresh(integration)
    return integration


# --- GitHub OAuth ---


@router.post("/github/authorize")
def github_authorize(
    redirect_uri: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Generate a GitHub OAuth authorization URL."""
    settings = get_settings()
    if not settings.github_client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub OAuth not configured",
        )

    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(GITHUB_SCOPES),
    }
    auth_url = f"{GITHUB_AUTH_URL}?{urlencode(params)}"
    return {"authorization_url": auth_url}


@router.post("/github/callback", response_model=IntegrationResponse)
def github_callback(
    callback: OAuthCallbackRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IntegrationResponse:
    """Exchange a GitHub OAuth authorization code for a token."""
    settings = get_settings()

    response = httpx.post(
        GITHUB_TOKEN_URL,
        data={
            "code": callback.code,
            "client_id": settings.github_client_id,
            "client_secret": settings.github_client_secret,
            "redirect_uri": callback.redirect_uri,
        },
        headers={"Accept": "application/json"},
    )

    if response.status_code != 200:
        log_audit(
            db,
            "oauth_callback",
            user_id=current_user.id,
            success=False,
            error_details=f"GitHub token exchange failed: {response.text}",
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to exchange authorization code",
        )

    token_data = response.json()
    access_token = token_data.get("access_token")
    scopes = token_data.get("scope", "")

    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No access token in response",
        )

    integration = _upsert_integration(
        db,
        user_id=current_user.id,
        provider=IntegrationProvider.GITHUB.value,
        access_token=access_token,
        scopes=scopes,
    )

    log_audit(
        db,
        "oauth_callback",
        user_id=current_user.id,
        integration_id=integration.id,
        metadata={"provider": IntegrationProvider.GITHUB.value},
    )

    db.commit()
    db.refresh(integration)
    return integration


# --- Disconnect / Panic ---


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_integration(
    integration_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Disconnect an integration. Revokes token at provider and deletes record."""
    integration = _get_user_integration(db, integration_id, current_user.id)

    _revoke_at_provider(integration)

    log_audit(
        db,
        "integration_disconnect",
        user_id=current_user.id,
        integration_id=integration.id,
        metadata={"provider": integration.provider},
    )

    db.delete(integration)
    db.commit()


@router.post("/panic", status_code=status.HTTP_204_NO_CONTENT)
def panic_revoke_all(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Emergency: revoke ALL integration tokens and deactivate everything.

    Per spec: "Admin endpoint that revokes all integration tokens
    and invalidates all sessions simultaneously."
    """
    integrations = (
        db.query(Integration)
        .filter(Integration.user_id == current_user.id)
        .all()
    )

    for integration in integrations:
        _revoke_at_provider(integration)
        integration.is_active = False
        integration.status = "disabled"
        integration.encrypted_auth_token = None
        integration.encrypted_refresh_token = None

    log_audit(
        db,
        "panic_revoke",
        user_id=current_user.id,
        metadata={"integrations_revoked": len(integrations)},
    )

    db.commit()


@router.post("/{integration_id}/test", response_model=IntegrationHealthResponse)
async def test_integration(
    integration_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IntegrationHealthResponse:
    """Trigger a test sync to verify integration health."""
    integration = _get_user_integration(db, integration_id, current_user.id)

    from app.services.connectors.github import GitHubConnector
    from app.services.connectors.gmail import GmailConnector
    from app.services.connectors.google_calendar import GoogleCalendarConnector

    connector_map = {
        IntegrationProvider.GOOGLE_CALENDAR.value: GoogleCalendarConnector,
        IntegrationProvider.GMAIL.value: GmailConnector,
        IntegrationProvider.GITHUB.value: GitHubConnector,
    }

    connector_cls = connector_map.get(integration.provider)
    if not connector_cls:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No connector for provider: {integration.provider}",
        )

    connector = connector_cls(integration)
    authenticated = await connector.authenticate()

    if not authenticated:
        integration.status = "failed"

    log_audit(
        db,
        "integration_test",
        user_id=current_user.id,
        integration_id=integration.id,
        success=authenticated,
        metadata={"provider": integration.provider},
    )

    db.commit()
    db.refresh(integration)

    return IntegrationHealthResponse(
        provider=integration.provider,
        status=integration.status,
        last_synced_at=integration.last_synced_at,
        is_active=integration.is_active,
    )


# --- Helpers ---


def _get_user_integration(
    db: Session, integration_id: str, user_id: str
) -> Integration:
    """Fetch an integration owned by the given user, or raise 404."""
    integration = (
        db.query(Integration)
        .filter(
            Integration.id == integration_id,
            Integration.user_id == user_id,
        )
        .first()
    )
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found",
        )
    return integration


def _upsert_integration(
    db: Session,
    *,
    user_id: str,
    provider: str,
    access_token: str,
    refresh_token: str | None = None,
    scopes: str = "",
) -> Integration:
    """Create or update an integration with encrypted tokens."""
    integration = (
        db.query(Integration)
        .filter(
            Integration.user_id == user_id,
            Integration.provider == provider,
        )
        .first()
    )

    encrypted_access = encrypt_token(access_token)
    encrypted_refresh = encrypt_token(refresh_token) if refresh_token else None

    if integration:
        integration.encrypted_auth_token = encrypted_access
        if encrypted_refresh:
            integration.encrypted_refresh_token = encrypted_refresh
        integration.scopes = scopes
        integration.status = "healthy"
        integration.error_count = 0
        integration.last_error = None
        integration.is_active = True
    else:
        integration = Integration(
            user_id=user_id,
            provider=provider,
            encrypted_auth_token=encrypted_access,
            encrypted_refresh_token=encrypted_refresh,
            scopes=scopes,
            status="healthy",
        )
        db.add(integration)

    return integration


def _revoke_at_provider(integration: Integration) -> None:
    """Best-effort token revocation at the provider.

    Failures are logged but do not prevent disconnection.
    """
    try:
        if not integration.encrypted_auth_token:
            return

        token = decrypt_token(integration.encrypted_auth_token)

        if integration.provider in (
            IntegrationProvider.GOOGLE_CALENDAR.value,
            IntegrationProvider.GMAIL.value,
        ):
            httpx.post(GOOGLE_REVOKE_URL, params={"token": token})
        elif integration.provider == IntegrationProvider.GITHUB.value:
            settings = get_settings()
            httpx.delete(
                f"https://api.github.com/applications/{settings.github_client_id}/token",
                auth=(settings.github_client_id, settings.github_client_secret),
                json={"access_token": token},
            )
    except Exception as e:
        logger.warning(
            "Failed to revoke token at provider %s: %s",
            integration.provider, e,
        )
