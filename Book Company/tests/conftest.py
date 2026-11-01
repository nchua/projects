"""Shared fixtures."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from bookgen.craft import PROJECT_ROOT
from bookgen.manifest import read_manifest
from bookgen.models import StageId, Value
from bookgen.stages import run_range
from bookgen.stages.base import StageContext
from bookgen.stages.s00_intake import with_series_id


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


@pytest.fixture
def demo_series(tmp_path: Path, demo_family_path: Path) -> StageContext:
    """A freshly initialised demo series (S0) under ``tmp_path``, value perseverance."""
    init = with_series_id(StageContext(base_dir=tmp_path, family_path=demo_family_path))
    run_range(init, [StageId.S0])
    return StageContext(series_id=init.series_id, base_dir=tmp_path, value=Value.PERSEVERANCE)


def open_flags(ctx: StageContext, ep: int = 1) -> list[str]:
    """Open flag codes in an episode's manifest."""
    return [f.code for f in read_manifest(ctx.paths.manifest(ep), ep).flags if not f.resolved]
