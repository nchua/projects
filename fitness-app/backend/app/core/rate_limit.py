"""
Shared slowapi Limiter instance.

Lives in its own module so both `main.py` (to wire into `app.state`) and
API modules (to attach `@limiter.limit(...)` decorators) can reference the
same instance. Without this, decorator and app-level state would diverge
and slowapi header injection would silently fail.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

# Single source of truth for rate-limit state.
limiter = Limiter(key_func=get_remote_address)

# Brute-force protection policy for auth endpoints.
AUTH_RATE_LIMIT = "5/10minutes"
