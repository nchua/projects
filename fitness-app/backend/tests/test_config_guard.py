"""Tests for the production config guard in app.core.config.

Ensures the app refuses to boot in production with a default SECRET_KEY or
with DEBUG=True, while still allowing local/staging to use defaults.
"""
import importlib
import os
import sys

import pytest

from app.core.config import DEFAULT_SECRET_KEY


def _reload_config(env: dict):
    """Re-import app.core.config with a patched environ."""
    for k in ("RAILWAY_ENVIRONMENT_NAME", "SECRET_KEY", "JWT_SECRET_KEY", "DEBUG"):
        os.environ.pop(k, None)
    os.environ.update(env)
    sys.modules.pop("app.core.config", None)
    return importlib.import_module("app.core.config")


def test_non_production_allows_defaults():
    # No Railway env -> no guard fires even with default secret + DEBUG=true.
    mod = _reload_config({"SECRET_KEY": DEFAULT_SECRET_KEY, "DEBUG": "true"})
    assert mod.settings.DEBUG is True
    assert mod.settings.SECRET_KEY == DEFAULT_SECRET_KEY


def test_staging_allows_defaults():
    mod = _reload_config({
        "RAILWAY_ENVIRONMENT_NAME": "staging",
        "SECRET_KEY": DEFAULT_SECRET_KEY,
        "DEBUG": "true",
    })
    assert mod.settings.DEBUG is True


def test_production_rejects_default_secret():
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        _reload_config({
            "RAILWAY_ENVIRONMENT_NAME": "production",
            "SECRET_KEY": DEFAULT_SECRET_KEY,
            "DEBUG": "false",
        })


def test_production_rejects_debug_true():
    with pytest.raises(RuntimeError, match="DEBUG"):
        _reload_config({
            "RAILWAY_ENVIRONMENT_NAME": "production",
            "SECRET_KEY": "real-strong-secret",
            "DEBUG": "true",
        })


def test_production_allows_proper_config():
    mod = _reload_config({
        "RAILWAY_ENVIRONMENT_NAME": "production",
        "SECRET_KEY": "real-strong-secret",
        "DEBUG": "false",
    })
    assert mod.settings.DEBUG is False
    assert mod.settings.SECRET_KEY == "real-strong-secret"
