"""
Request context utilities.

Provides a contextvar for the per-request correlation ID so that logging
filters and error reporters (Sentry) can tag events even from deep within
request handling without explicit propagation.
"""
from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Header used to both accept and emit the correlation ID.
REQUEST_ID_HEADER = "X-Request-ID"

# Module-level contextvar; default "-" so loggers have something to print
# outside request scope (e.g. startup logs).
_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    """Return the current request's correlation ID, or '-' outside request scope."""
    return _request_id_ctx.get()


def set_request_id(request_id: str) -> None:
    """Set the current request's correlation ID (used by middleware)."""
    _request_id_ctx.set(request_id)


def _generate_request_id() -> str:
    return uuid.uuid4().hex


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Generate/propagate a correlation ID for every request.

    - If the incoming request carries an `X-Request-ID` header, echo it back.
    - Otherwise, generate a new uuid4 hex.
    - The ID is stashed in a contextvar so log records + Sentry scopes
      can pick it up without explicit threading.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER)
        request_id = incoming if incoming else _generate_request_id()
        token = _request_id_ctx.set(request_id)

        # Make the ID accessible on request.state for handlers.
        request.state.request_id = request_id

        # Optional Sentry tagging — import lazily so local dev without
        # the SDK installed (or without a DSN) is a no-op.
        try:  # pragma: no cover - depends on optional dep
            import sentry_sdk

            sentry_sdk.set_tag("request_id", request_id)
        except Exception:
            pass

        try:
            response = await call_next(request)
        except Exception:
            # Ensure contextvar resets even on failure. The outer framework
            # exception handler will emit its own Response; we can't attach
            # the header to it from here, but the ID still shows up in logs
            # via the contextvar + filter (flushed before reset).
            _request_id_ctx.reset(token)
            raise

        response.headers[REQUEST_ID_HEADER] = request_id
        _request_id_ctx.reset(token)
        return response


class RequestIdLogFilter(logging.Filter):
    """
    Inject `request_id` into every LogRecord so format strings can use
    `%(request_id)s`. Outside request scope this is `-`.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def install_logging_filter(root_logger: Optional[logging.Logger] = None) -> None:
    """
    Attach the request-id filter to the root logger and all existing
    handlers so every log line carries `[req_id=...]`.
    """
    root_logger = root_logger or logging.getLogger()
    log_filter = RequestIdLogFilter()
    root_logger.addFilter(log_filter)
    for handler in root_logger.handlers:
        handler.addFilter(log_filter)
