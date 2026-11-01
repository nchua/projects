"""The ImageProvider protocol and what every adapter shares (SPEC §8.3, §8.6).

Images are passed as file paths, since every artifact lives on disk (§3.1).
Adapters never see craft text: the brief-to-prompt rendering lives in
``stages/s07_generate.py``, so a provider swap is one new file here.

Seam: an adapter is one module with a class that has ``name``, ``model``,
``generate``, ``edit``, ``upscale`` and ``capabilities``, registered in
``bookgen/providers/images/__init__.py``. Keys come from the provider's env var
(read when a call is made, never stored). A refusal is a result
(``refused=True``), not an exception (§7.5: the bake-off counts them).
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import Field

from bookgen.models import Model

ASPECT_PIXELS = 1_572_864
"""Target pixel count for an aspect-derived size (~1.5 MP; upscaling is S9's job)."""


class ImageProviderError(RuntimeError):
    """A provider call failed for a reason other than a policy refusal."""


class ImageResult(Model):
    """One image an adapter produced, or one it was refused."""

    path: Path | None = Field(
        default=None, description="Where the image was written; None if refused."
    )
    provider: str = Field(description="Provider name, e.g. 'gemini'.")
    model: str = Field(description="Provider model id.")
    seed: int | None = Field(default=None, description="Seed, if the provider exposes one.")
    cost_usd: float = Field(
        default=0.0, ge=0, description="Cost of this image (estimate if unbilled)."
    )
    refused: bool = Field(default=False, description="Provider declined the prompt (§7.5).")
    refusal_reason: str = Field(default="", description="What the provider said, if refused.")
    latency_s: float = Field(default=0.0, ge=0, description="Wall time of the call that made it.")


class ProviderCapabilities(Model):
    """What a provider supports; the bake-off (§8.3) and S7 read this."""

    max_references: int = Field(ge=0, description="Max reference images per call.")
    aspects: list[str] = Field(description="Supported aspect ratios, e.g. ['16:9', '1:1'].")
    max_px: int = Field(gt=0, description="Longest output edge in pixels.")
    supports_edit: bool = Field(description="Whether ``edit`` is implemented.")
    usd_per_image: float = Field(
        ge=0, description="List-price estimate per image at the default size [VERIFY-4]."
    )


@runtime_checkable
class ImageProvider(Protocol):
    """A provider-agnostic image generator (D9)."""

    name: str
    """Short provider name recorded in manifests."""

    model: str
    """Provider model id in use (env-overridable per adapter)."""

    def generate(
        self,
        prompt: str,
        references: list[Path],
        aspect: str,
        n: int,
        seed: int | None,
        out: Path,
    ) -> list[ImageResult]:
        """Generate ``n`` candidates for ``prompt`` with ``references`` at ``aspect``.

        Candidate ``k`` (1-based) is written to ``candidate_path(out, k, ext)``.
        """
        ...

    def edit(self, image: Path, prompt: str, references: list[Path], out: Path) -> ImageResult:
        """Make a targeted fix to one image (single-spread regeneration), written at ``out``."""
        ...

    def upscale(self, image: Path, factor: int) -> Path:
        """Upscale ``image`` by ``factor``; optional per provider (may raise)."""
        ...

    def capabilities(self) -> ProviderCapabilities:
        """Report reference limits, aspects, size, edit support and list price."""
        ...


def candidate_path(out: Path, k: int, ext: str = "png") -> Path:
    """``<out>_c<k>.<ext>``: e.g. ``images/s07`` -> ``images/s07_c2.png`` (§3.3 S7 naming)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    return out.with_name(f"{out.name}_c{k}.{ext}")


def require_key(env_var: str) -> str:
    """The API key in ``env_var``, or a clear error naming it (never logged)."""
    key = os.environ.get(env_var, "")
    if not key:
        raise ImageProviderError(f"{env_var} is not set")
    return key


def ratio(aspect: str) -> float:
    """Width over height of an aspect string, e.g. 16:9 -> 1.78."""
    w, h = aspect.split(":")
    return float(w) / float(h)


def nearest_aspect(aspect: str, supported: list[str]) -> str:
    """The supported aspect closest to ``aspect`` (a 2:1 spread may become 16:9 or 21:9)."""
    want = ratio(aspect)
    return min(supported, key=lambda a: abs(ratio(a) - want))


def size_for(aspect: str, multiple: int = 16, pixels: int = ASPECT_PIXELS) -> tuple[int, int]:
    """Width and height near ``pixels`` total at ``aspect``, rounded to ``multiple``."""
    r = ratio(aspect)
    h = (pixels / r) ** 0.5
    w = h * r
    return (round(w / multiple) * multiple, round(h / multiple) * multiple)


def mime_for(path: Path) -> str:
    """Image MIME type from the file extension."""
    ext = path.suffix.lower().lstrip(".")
    return {"jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext, "image/png")


def timed[T](fn: Callable[[], T]) -> tuple[T, float]:
    """Call ``fn``; return its result and the wall time in seconds."""
    start = time.monotonic()
    out = fn()
    return out, time.monotonic() - start
