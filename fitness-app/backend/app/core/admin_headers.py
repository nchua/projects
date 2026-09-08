"""
Response headers for the owner console origin (control-plane spec §10.1).

A pure-ASGI middleware so the headers land on *every* ``/admin/*`` response —
including the 401/403/422/429 bodies the exception handlers build, which a
router-level ``Response`` dependency would miss. ``Cache-Control: no-store``
keeps user emails and audit JSON out of browser and proxy caches;
``X-Frame-Options: DENY`` keeps the console out of frames. The CSP allows
scripts and styles from this origin only — no ``'unsafe-inline'``, which is
why the console ships ``admin.js`` / ``admin.css`` as separate files (W3).
It lands on the JSON routes too, where it is inert.
"""
from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

ADMIN_PREFIX = "/admin"
ADMIN_CSP = "default-src 'self'; script-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
ADMIN_RESPONSE_HEADERS = {
    "Cache-Control": "no-store",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": ADMIN_CSP,
}


def is_admin_path(path: str) -> bool:
    """True for ``/admin`` and anything beneath it (not ``/administrator``)."""
    return path == ADMIN_PREFIX or path.startswith(ADMIN_PREFIX + "/")


class AdminResponseHeadersMiddleware:
    """Stamp :data:`ADMIN_RESPONSE_HEADERS` on every ``/admin/*`` HTTP response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not is_admin_path(scope.get("path", "")):
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in ADMIN_RESPONSE_HEADERS.items():
                    headers[name] = value
            await send(message)

        await self.app(scope, receive, send_with_headers)
