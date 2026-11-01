"""Filesystem layout for generated artifacts (SPEC §3.4).

Seam: every stage resolves artifact paths through ``SeriesPaths``; nothing
hard-codes ``series/...`` strings. The root is ``BOOKGEN_SERIES_DIR`` or
``<project>/series`` (gitignored).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from bookgen.craft import PROJECT_ROOT


def series_base() -> Path:
    """Return the directory that holds every series (``BOOKGEN_SERIES_DIR`` or ``series/``)."""
    return Path(os.environ.get("BOOKGEN_SERIES_DIR", str(PROJECT_ROOT / "series")))


@dataclass(frozen=True)
class SeriesPaths:
    """Paths inside ``series/<series_id>/`` per §3.4."""

    root: Path
    """The series directory, ``series/<series_id>/``."""

    @classmethod
    def for_series(cls, series_id: str, base: Path | None = None) -> SeriesPaths:
        """Build paths for ``series_id`` under ``base`` (default ``series_base()``)."""
        return cls((base or series_base()) / series_id)

    @property
    def profile(self) -> Path:
        """``family/profile.json`` (S0)."""
        return self.root / "family" / "profile.json"

    def character_dir(self, person_id: str) -> Path:
        """``characters/<person_id>/`` (S1-S2)."""
        return self.root / "characters" / person_id

    def appearance(self, person_id: str) -> Path:
        """``characters/<person_id>/appearance.json`` (S1, or S0 for hand-written L1 cards)."""
        return self.character_dir(person_id) / "appearance.json"

    @property
    def series_meta(self) -> Path:
        """``series/`` inside the series root: bible, ledger, style, anchors (S3, S13)."""
        return self.root / "series"

    @property
    def bible(self) -> Path:
        """``series/bible.json`` (S3)."""
        return self.series_meta / "bible.json"

    @property
    def ledger(self) -> Path:
        """``series/ledger.json`` (§4.3, S13)."""
        return self.series_meta / "ledger.json"

    @property
    def style(self) -> Path:
        """``series/style.json``: the locked style bible (D5)."""
        return self.series_meta / "style.json"

    def episode_dir(self, episode: int) -> Path:
        """``epNN/`` for an episode number."""
        return self.root / f"ep{episode:02d}"

    def manifest(self, episode: int) -> Path:
        """``epNN/manifest.json`` (§3.1)."""
        return self.episode_dir(episode) / "manifest.json"

    def dirs(self, person_ids: list[str], episode: int) -> list[Path]:
        """Every directory §3.4 names, for the given people and episode."""
        out = [self.root / "family", self.series_meta, self.series_meta / "style_anchors"]
        for pid in person_ids:
            d = self.character_dir(pid)
            out += [d, d / "sheet_crops", d / "candidates"]
        ep = self.episode_dir(episode)
        out += [ep, ep / "images", ep / "print", ep / "logs"]
        return out
