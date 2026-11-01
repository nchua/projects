"""A no-network ImageProvider for tests and dry runs: writes tiny valid PNGs.

``refuse_when`` lets a test simulate a policy refusal for prompts containing a word.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

from bookgen.providers.images.base import (
    ImageResult,
    ProviderCapabilities,
    candidate_path,
    size_for,
)


def write_png(path: Path, width: int, height: int, rgb: tuple[int, int, int]) -> Path:
    """Write a solid-colour PNG (no imaging dependency); returns ``path``."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        """One length-prefixed, CRC-suffixed PNG chunk."""
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    row = b"\x00" + bytes(rgb) * width
    pixels = zlib.compress(row * height)
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", pixels) + chunk(b"IEND", b"")
    )
    return path


def png_size(path: Path) -> tuple[int, int]:
    """Width and height from a PNG header."""
    width, height = struct.unpack(">II", path.read_bytes()[16:24])
    return width, height


class FakeImageProvider:
    """Implements ``ImageProvider`` with small solid PNGs; records every call."""

    name = "fake"
    model = "fake-1"

    def __init__(self, refuse_when: str | None = None, usd_per_image: float = 0.01) -> None:
        """Refuse prompts containing ``refuse_when``; charge ``usd_per_image``."""
        self.refuse_when = refuse_when
        self.usd_per_image = usd_per_image
        self.calls: list[dict[str, object]] = []

    def generate(
        self,
        prompt: str,
        references: list[Path],
        aspect: str,
        n: int,
        seed: int | None,
        out: Path,
    ) -> list[ImageResult]:
        """``n`` tiny PNGs at ``aspect`` (scaled down 16x), or ``n`` refusals."""
        self.calls.append({"prompt": prompt, "references": references, "aspect": aspect, "n": n})
        if self.refuse_when and self.refuse_when in prompt:
            return [
                ImageResult(
                    provider=self.name, model=self.model, refused=True, refusal_reason="fake policy"
                )
                for _ in range(n)
            ]
        w, h = size_for(aspect)
        return [
            ImageResult(
                path=write_png(candidate_path(out, k), w // 16, h // 16, (200, 150, 100)),
                provider=self.name,
                model=self.model,
                seed=seed,
                cost_usd=self.usd_per_image,
            )
            for k in range(1, n + 1)
        ]

    def edit(self, image: Path, prompt: str, references: list[Path], out: Path) -> ImageResult:
        """One fake edit."""
        return self.generate(prompt, [image, *references], "1:1", 1, None, out)[0]

    def upscale(self, image: Path, factor: int) -> Path:
        """Not supported."""
        raise NotImplementedError("fake provider does not upscale")

    def capabilities(self) -> ProviderCapabilities:
        """Generous limits so tests exercise reference selection, not truncation."""
        return ProviderCapabilities(
            max_references=8,
            aspects=["1:1", "16:9", "21:9"],
            max_px=2048,
            supports_edit=True,
            usd_per_image=self.usd_per_image,
        )
