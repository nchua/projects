"""Audit logging for sensitive operations.

Per spec: Log every OAuth token usage (without token values),
every Claude API call (without content), every data sync,
and every token refresh.
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


def log_audit(
    db: Session,
    action_type: str,
    *,
    user_id: str | None = None,
    integration_id: str | None = None,
    success: bool = True,
    error_details: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    """Record an audit log entry for a sensitive operation.

    Args:
        db: Database session.
        action_type: What happened (e.g., "oauth_callback", "sync",
            "token_refresh", "ai_extraction", "panic_revoke").
        user_id: The user who triggered or owns the operation.
        integration_id: Related integration, if any.
        success: Whether the operation succeeded.
        error_details: Error message if it failed.
        metadata: Structured metadata (NEVER include token values).

    Returns:
        The created AuditLog record.
    """
    entry = AuditLog(
        action_type=action_type,
        user_id=user_id,
        integration_id=integration_id,
        success=success,
        error_details=error_details,
        metadata_=metadata,
    )
    db.add(entry)
    db.flush()

    log_msg = "AUDIT: %s user=%s integration=%s success=%s"
    log_args = (action_type, user_id, integration_id, success)

    if success:
        logger.info(log_msg, *log_args)
    else:
        logger.warning(log_msg + " error=%s", *log_args, error_details)

    return entry
