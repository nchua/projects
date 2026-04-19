"""
Shared slowapi Limiter instance.

Lives in its own module so both `main.py` (to wire into `app.state`) and
API modules (to attach `@limiter.limit(...)` decorators) can reference the
same instance. Without this, decorator and app-level state would diverge
and slowapi header injection would silently fail.
"""
from starlette.requests import Request

from slowapi import Limiter


def _client_ip(request: Request) -> str:
    """Best-effort true client IP honoring Railway's edge proxy.

    slowapi's default `get_remote_address` returns `request.client.host`,
    which behind Railway is the proxy's IP — so the rate limit collapses
    to a single global bucket and legitimate users share each other's
    quota. Read the first X-Forwarded-For hop instead, with graceful
    fallback to the peer address for local dev / test clients that don't
    set the header.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        # First entry is the original client; subsequent entries are proxies.
        first = xff.split(",")[0].strip()
        if first:
            return first
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


# Single source of truth for rate-limit state.
limiter = Limiter(key_func=_client_ip)

# Login brute-force protection — tight, because the attack shape is
# per-account credential stuffing. Shared-NAT false positives are
# acceptable here: 5 failed logins in 10 min from any network hop is
# strong signal of abuse.
LOGIN_RATE_LIMIT = "5/10minutes"

# Registration is softer on purpose. Gyms, coffee shops, college dorms,
# and corporate VPNs all egress through a single IP; 5/10min on register
# would lock out signup bursts from a team demo or family sharing a
# connection. Still tight enough to deter mass account creation.
REGISTER_RATE_LIMIT = "20/10minutes"

# Back-compat alias: older test file still imports AUTH_RATE_LIMIT.
AUTH_RATE_LIMIT = LOGIN_RATE_LIMIT
