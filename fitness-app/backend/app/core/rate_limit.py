"""
Shared slowapi Limiter instance.

Lives in its own module so both `main.py` (to wire into `app.state`) and
API modules (to attach `@limiter.limit(...)` decorators) can reference the
same instance. Without this, decorator and app-level state would diverge
and slowapi header injection would silently fail.
"""
from slowapi import Limiter
from starlette.requests import Request


def _client_ip(request: Request) -> str:
    """Best-effort true client IP honoring Railway's edge proxy.

    slowapi's default `get_remote_address` returns `request.client.host`,
    which behind Railway is the proxy's IP — so the rate limit collapses
    to a single global bucket and legitimate users share each other's
    quota.

    Security note: trusting the *first* X-Forwarded-For entry is unsafe
    because clients control the header. An attacker can spoof
    `X-Forwarded-For: 1.2.3.<random>` to rotate the rate-limit key and
    bypass brute-force protection. Instead we take the *last* hop, which
    is what the nearest trusted proxy (Railway's edge) appended — that
    value is the real peer address from the proxy's perspective and
    cannot be forged by the client.

    This assumes Railway's edge appends the true client IP to the end of
    XFF. If the deployment topology changes (e.g. additional proxies in
    front of Railway), revisit by introducing a TRUSTED_PROXY_COUNT env
    var and skipping that many hops from the end.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        hops = [h.strip() for h in xff.split(",") if h.strip()]
        if hops:
            return hops[-1]
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


# Single source of truth for rate-limit state.
# TODO: in-memory storage is per-worker and resets on deploy. For real brute-force protection,
# wire Redis via storage_uri="redis://...". Tracked in PR #8 review.
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
