"""Tests for the production config guard in app.core.config.

Ensures the app refuses to boot in production with a default SECRET_KEY or
with DEBUG=True, while still allowing local/staging to use defaults.
"""
import importlib
import sys

import pytest

from app.core.config import DEFAULT_SECRET_KEY

_GUARD_ENV_VARS = ("RAILWAY_ENVIRONMENT_NAME", "SECRET_KEY", "JWT_SECRET_KEY", "DEBUG")


@pytest.fixture
def reload_config(monkeypatch):
    """Factory that re-imports app.core.config under a patched environ.

    monkeypatch restores os.environ after each test; the fixture teardown
    restores the original app.core.config module object in sys.modules so
    the throwaway re-imports done here never leak into other tests (or into
    app modules that resolve `app.core.config` lazily).
    """
    original_module = sys.modules.get("app.core.config")

    def _reload(env: dict):
        for key in _GUARD_ENV_VARS:
            monkeypatch.delenv(key, raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        sys.modules.pop("app.core.config", None)
        return importlib.import_module("app.core.config")

    yield _reload

    sys.modules.pop("app.core.config", None)
    if original_module is not None:
        sys.modules["app.core.config"] = original_module


def test_non_production_allows_defaults(reload_config):
    # No Railway env -> no guard fires even with default secret + DEBUG=true.
    mod = reload_config({"SECRET_KEY": DEFAULT_SECRET_KEY, "DEBUG": "true"})
    assert mod.settings.DEBUG is True
    assert mod.settings.SECRET_KEY == DEFAULT_SECRET_KEY


def test_staging_allows_defaults(reload_config):
    mod = reload_config({
        "RAILWAY_ENVIRONMENT_NAME": "staging",
        "SECRET_KEY": DEFAULT_SECRET_KEY,
        "DEBUG": "true",
    })
    assert mod.settings.DEBUG is True


def test_production_rejects_default_secret(reload_config):
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        reload_config({
            "RAILWAY_ENVIRONMENT_NAME": "production",
            "SECRET_KEY": DEFAULT_SECRET_KEY,
            "DEBUG": "false",
        })


def test_production_rejects_debug_true(reload_config):
    with pytest.raises(RuntimeError, match="DEBUG"):
        reload_config({
            "RAILWAY_ENVIRONMENT_NAME": "production",
            "SECRET_KEY": "real-strong-secret",
            "DEBUG": "true",
        })


def test_production_allows_proper_config(reload_config):
    mod = reload_config({
        "RAILWAY_ENVIRONMENT_NAME": "production",
        "SECRET_KEY": "real-strong-secret",
        "DEBUG": "false",
    })
    assert mod.settings.DEBUG is False
    assert mod.settings.SECRET_KEY == "real-strong-secret"
