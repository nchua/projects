"""Shared fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from bookgen.craft import PROJECT_ROOT


@pytest.fixture
def demo_family_path() -> Path:
    """Path to the fixture family."""
    return PROJECT_ROOT / "examples" / "family_demo.json"
