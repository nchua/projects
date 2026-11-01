"""Shared fixtures."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from bookgen.craft import PROJECT_ROOT


@pytest.fixture
def demo_family_path() -> Path:
    """Path to the fixture family."""
    return PROJECT_ROOT / "examples" / "family_demo.json"


@pytest.fixture
def demo_family_raw(demo_family_path: Path) -> dict[str, Any]:
    """The fixture family as a plain dict, for building variants."""
    return json.loads(demo_family_path.read_text())


@pytest.fixture
def write_family(tmp_path: Path) -> Callable[[dict[str, Any]], Path]:
    """Write a family dict to a temp file and return its path."""

    def _write(data: dict[str, Any]) -> Path:
        path = tmp_path / "family.json"
        path.write_text(json.dumps(data))
        return path

    return _write
