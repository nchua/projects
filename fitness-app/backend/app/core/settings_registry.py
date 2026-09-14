"""
The editable-settings registry (console v2 spec §4.5, §6.5).

One entry per key the owner can change from the console. Each entry names
the ``Settings`` attribute it shadows (the env / code fallback the resolver
falls through to), its type and bounds for validation, its group on the
Settings screen, and its tier (``destructive`` keys need the step-up
password). ``inactive_after_days`` is the one key with no ``Settings``
attribute: it is new in v2 and its code default lives here.

To add an editable setting: one ``SettingSpec`` below; the resolver
(``settings_service.get``), ``GET /admin/settings`` and
``PATCH /admin/settings/{key}`` pick it up from the registry, and
``test_admin_settings`` walks the registry for types and bounds.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.utils import split_csv

GROUP_SCANNER = "scanner"
GROUP_ACCOUNTS = "accounts"
GROUP_SWITCHES = "switches"

TIER_STANDARD = "standard"
TIER_DESTRUCTIVE = "destructive"

TYPE_INT = "int"
TYPE_SECONDS = "seconds"
TYPE_BOOL = "bool"
TYPE_CSV = "csv"

INACTIVE_AFTER_DAYS = "inactive_after_days"


@dataclass(frozen=True)
class SettingSpec:
    """One console-editable setting."""

    key: str
    label: str
    group: str
    type: str
    tier: str
    attr: Optional[str] = None      # the ``Settings`` attribute shadowed (None: registry default)
    default: Any = None             # code default when ``attr`` is None
    min: Optional[int] = None
    max: Optional[int] = None
    allowed: Tuple[str, ...] = ()   # csv: the tokens accepted (empty = any word)

    def fallback(self) -> Any:
        """The env / code value that applies when no ``app_settings`` row exists."""
        return self.default if self.attr is None else getattr(settings, self.attr)


def _spec(key: str, label: str, group: str, type_: str, tier: str, **kw: Any) -> SettingSpec:
    return SettingSpec(key=key, label=label, group=group, type=type_, tier=tier, attr=kw.pop("attr", key), **kw)


SETTINGS: List[SettingSpec] = [
    # ── Scanner (standard tier) ──
    _spec("FREE_MONTHLY_SCANS", "Free scans per month", GROUP_SCANNER, TYPE_INT, TIER_STANDARD, min=0, max=1000),
    _spec("DAILY_SCREENSHOT_LIMIT", "Daily scan cap per hunter", GROUP_SCANNER, TYPE_INT, TIER_STANDARD, min=1, max=1000),
    _spec("COOLDOWN_SECONDS", "Cooldown between scans", GROUP_SCANNER, TYPE_SECONDS, TIER_STANDARD, min=0, max=3600),
    _spec("PURCHASE_MAX_CREDITS_PER_DAY", "Purchased credits per day", GROUP_SCANNER, TYPE_INT, TIER_STANDARD, min=0, max=10000),
    _spec("PURCHASE_MAX_VERIFICATIONS_PER_DAY", "Purchase verifications per day", GROUP_SCANNER, TYPE_INT, TIER_STANDARD, min=1, max=1000),
    _spec("ANTHROPIC_DAILY_CALL_CEILING", "Anthropic daily call ceiling", GROUP_SCANNER, TYPE_INT, TIER_STANDARD, min=0, max=100000),
    _spec("ANTHROPIC_DAILY_CALL_WARN_PERCENT", "Ceiling warning percent", GROUP_SCANNER, TYPE_INT, TIER_STANDARD, min=1, max=100),
    # ── Accounts ──
    _spec(INACTIVE_AFTER_DAYS, "Inactive after (days)", GROUP_ACCOUNTS, TYPE_INT, TIER_STANDARD, attr=None, default=30, min=1, max=3650),
    _spec("PURGE_GRACE_DAYS", "Purge grace (days)", GROUP_ACCOUNTS, TYPE_INT, TIER_DESTRUCTIVE, min=1, max=365),
    # ── Switches (destructive tier) ──
    _spec("SCREENSHOT_PROCESSING_ENABLED", "Screenshot processing", GROUP_SWITCHES, TYPE_BOOL, TIER_DESTRUCTIVE),
    _spec("PURGE_SWEEP_ENABLED", "Purge sweep on deploy", GROUP_SWITCHES, TYPE_BOOL, TIER_DESTRUCTIVE),
    _spec("PURCHASE_REQUIRE_JWS", "Require signed receipts", GROUP_SWITCHES, TYPE_BOOL, TIER_DESTRUCTIVE),
    _spec(
        "PURCHASE_ALLOWED_ENVIRONMENTS", "Allowed purchase environments", GROUP_SWITCHES, TYPE_CSV,
        TIER_DESTRUCTIVE, allowed=("Production", "Sandbox", "Xcode"),
    ),
]

SETTINGS_REGISTRY: Dict[str, SettingSpec] = {spec.key: spec for spec in SETTINGS}


def coerce(spec: SettingSpec, value: Any) -> Any:
    """Validate ``value`` against ``spec`` and return it in its canonical Python type.

    Raises ``ValueError`` with a human message on a type or bounds violation;
    the PATCH route maps that to 422. Booleans are never accepted where an
    int is expected (``True`` is not ``1`` here), ints are never accepted as
    booleans, and a csv is a comma-separated string of allowed tokens.
    """
    if spec.type in (TYPE_INT, TYPE_SECONDS):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{spec.key} expects an integer")
        if spec.min is not None and value < spec.min:
            raise ValueError(f"{spec.key} must be at least {spec.min}")
        if spec.max is not None and value > spec.max:
            raise ValueError(f"{spec.key} must be at most {spec.max}")
        return value
    if spec.type == TYPE_BOOL:
        if not isinstance(value, bool):
            raise ValueError(f"{spec.key} expects true or false")
        return value
    if spec.type == TYPE_CSV:
        if not isinstance(value, str):
            raise ValueError(f"{spec.key} expects a comma-separated string")
        tokens = split_csv(value)
        if not tokens:
            raise ValueError(f"{spec.key} needs at least one value")
        unknown = [t for t in tokens if spec.allowed and t not in spec.allowed]
        if unknown:
            raise ValueError(f"{spec.key}: unknown value {unknown[0]} (allowed: {', '.join(spec.allowed)})")
        return ",".join(tokens)
    raise ValueError(f"unknown setting type {spec.type}")  # pragma: no cover - registry is static
