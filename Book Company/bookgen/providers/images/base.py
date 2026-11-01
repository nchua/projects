"""The ImageProvider protocol (SPEC §8.6). No adapters yet (session 3).

Images are passed as file paths, since every artifact lives on disk (§3.1).
Adapters never see craft text: the brief-to-prompt rendering lives in
``stages/s07_generate.py``, so a provider swap is one new file here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class ImageResult(BaseModel):
    """One image an adapter produced."""

    path: Path = Field(description="Where the adapter wrote the image.")
    provider: str = Field(description="Provider name, e.g. 'gemini'.")
    model: str = Field(description="Provider model id.")
    seed: int | None = Field(default=None, description="Seed, if the provider exposes one.")
    cost_usd: float = Field(default=0.0, ge=0, description="Cost of this image.")
    refused: bool = Field(default=False, description="Provider declined the prompt (§7.5).")


class ProviderCapabilities(BaseModel):
    """What a provider supports; the bake-off (§8.3) and S7 read this."""

    max_references: int = Field(ge=0, description="Max reference images per call.")
    aspects: list[str] = Field(description="Supported aspect ratios, e.g. ['2:1', '1:1'].")
    max_px: int = Field(gt=0, description="Longest output edge in pixels.")
    supports_edit: bool = Field(description="Whether ``edit`` is implemented.")


@runtime_checkable
class ImageProvider(Protocol):
    """A provider-agnostic image generator (D9)."""

    name: str
    """Short provider name recorded in manifests."""

    def generate(
        self, prompt: str, references: list[Path], aspect: str, n: int, seed: int | None
    ) -> list[ImageResult]:
        """Generate ``n`` candidates for ``prompt`` with ``references`` at ``aspect``."""
        ...

    def edit(self, image: Path, prompt: str, references: list[Path]) -> ImageResult:
        """Make a targeted fix to one image (single-spread regeneration)."""
        ...

    def upscale(self, image: Path, factor: int) -> Path:
        """Upscale ``image`` by ``factor``; optional per provider (may raise)."""
        ...

    def capabilities(self) -> ProviderCapabilities:
        """Report reference limits, aspects, size and edit support."""
        ...
