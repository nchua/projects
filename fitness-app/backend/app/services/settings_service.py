"""
The settings resolver (console v2 spec §6.5).

``get(db, key)`` answers the value that applies right now for one registry
key: the ``app_settings`` row when the owner has set one from the console,
else the env / code value on ``Settings``. One indexed primary-key read per
call and no cache (decision 8) — an edit is live on the next request, and a
test that monkeypatches ``settings.X`` keeps working because there is no row
to shadow it.

Every read site that used to touch ``settings.<KEY>`` for a registry key
goes through here: ``entitlement_service.default_scan_limits``,
``purge_service`` (grace, sweep gate), ``api/screenshot.py`` (kill switch,
Anthropic ceiling) and ``api/scan_balance.py`` (purchase caps, JWS policy).
The write side (``set_value`` / ``reset``) is called only by
``admin_mutation_service.update_setting``, which audits it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.settings_registry import SETTINGS_REGISTRY, SettingSpec, coerce
from app.core.utils import split_csv, utcnow
from app.models.app_setting import AppSetting

logger = logging.getLogger(__name__)

SOURCE_CONSOLE = "console"
SOURCE_ENV = "env"
SOURCE_CODE = "code"


@dataclass(frozen=True)
class Resolved:
    """A key's effective value, where it came from, and the fallback beneath it."""

    value: Any
    source: str                          # console | env | code
    default: Any                         # the env / code value that applies with no row
    updated_at: Optional[datetime] = None  # console rows only
    updated_by: Optional[str] = None


def spec_for(key: str) -> SettingSpec:
    """The registry entry, or ``KeyError`` for a key the console cannot edit."""
    return SETTINGS_REGISTRY[key]


def _row(db: Session, key: str) -> Optional[AppSetting]:
    return db.query(AppSetting).filter(AppSetting.key == key).first()


def _fallback_source(spec: SettingSpec) -> str:
    """``env`` when the Railway variable (or ``.env``) set the attribute, else ``code``."""
    if spec.attr is not None and spec.attr in settings.model_fields_set:
        return SOURCE_ENV
    return SOURCE_CODE


def override_rows(db: Session) -> Dict[str, AppSetting]:
    """Every console override at once (the Settings screen reads the table once)."""
    return {row.key: row for row in db.query(AppSetting).all()}


def resolve(db: Session, key: str, *, row: Optional[AppSetting] = None, prefetched: bool = False) -> Resolved:
    """Value + provenance for ``key``; pass ``row`` (``prefetched=True``) to skip the read."""
    spec = spec_for(key)
    default = spec.fallback()
    if not prefetched:
        row = _row(db, key)
    if row is None:
        return Resolved(value=default, source=_fallback_source(spec), default=default)
    try:
        value = coerce(spec, row.value)
    except ValueError as exc:
        # A row the registry no longer accepts (bounds tightened, a hand edit) must not
        # take the scanner or the console down: fall through and say so once per read.
        logger.warning("app_settings.%s ignored (%s); using the env / code value", key, exc)
        return Resolved(value=default, source=_fallback_source(spec), default=default)
    return Resolved(
        value=value, source=SOURCE_CONSOLE, default=default,
        updated_at=row.updated_at, updated_by=row.updated_by,
    )


def get(db: Session, key: str) -> Any:
    """The value in force for ``key``: ``app_settings`` row → ``settings.<KEY>`` → code."""
    return resolve(db, key).value


def csv_set(db: Session, key: str) -> set:
    """A csv-typed key as the set of its tokens."""
    return set(split_csv(str(get(db, key))))


def set_value(db: Session, key: str, value: Any, *, updated_by: Optional[str]) -> AppSetting:
    """Upsert the console override for ``key`` (flush, no commit). ``value`` is already coerced."""
    row = _row(db, key)
    if row is None:
        row = AppSetting(key=key, value=value, updated_at=utcnow(), updated_by=updated_by)
        db.add(row)
    else:
        row.value = value
        row.updated_at = utcnow()
        row.updated_by = updated_by
    db.flush()
    return row


def reset(db: Session, key: str) -> bool:
    """Delete the console override for ``key`` (flush, no commit). False when there was none."""
    row = _row(db, key)
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True
