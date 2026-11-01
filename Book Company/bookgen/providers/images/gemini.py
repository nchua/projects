"""Google Gemini image models ("Nano Banana Pro") via the Interactions REST API (§8.3).

Request shape per ai.google.dev/gemini-api/docs/image-generation (read 2026-11-01):
POST ``/v1beta/interactions`` with ``x-goog-api-key``; ``input`` is a text item plus
base64 image items; ``response_format`` sets ``aspect_ratio`` and ``image_size``.
One image per call, so ``n`` candidates are ``n`` calls. No seed parameter.
The docs don't say how a safety block is reported, so a 200 with no image is
treated as a refusal and its body is kept as the reason ``[VERIFY-2]``.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

import httpx2

from bookgen.providers.images.base import (
    ImageProviderError,
    ImageResult,
    ProviderCapabilities,
    candidate_path,
    mime_for,
    nearest_aspect,
    require_key,
    timed,
)

URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
ASPECTS = ["1:1", "3:2", "2:3", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]
"""Listed on the docs page; per-model support isn't broken down there [VERIFY-4]."""


def find_image(node: Any) -> dict[str, Any] | None:  # noqa: ANN401 - untyped JSON
    """The last ``{"type": "image", "data": ...}`` block anywhere in the response."""
    found = None
    if isinstance(node, dict):
        if node.get("type") == "image" and node.get("data"):
            found = node
        for value in node.values():
            found = find_image(value) or found
    elif isinstance(node, list):
        for value in node:
            found = find_image(value) or found
    return found


class GeminiProvider:
    """``ImageProvider`` for Gemini image models; key from ``GEMINI_API_KEY``."""

    name = "gemini"

    def __init__(self, client: httpx2.Client | None = None, model: str | None = None) -> None:
        """Use ``client`` (tests pass a mock transport) and ``model`` or the env default."""
        self.model = model or os.environ.get("BOOKGEN_GEMINI_MODEL", "gemini-3-pro-image")
        self.image_size = os.environ.get("BOOKGEN_GEMINI_IMAGE_SIZE", "2K")
        self._client = client or httpx2.Client(timeout=300)

    def _one(self, prompt: str, references: list[Path], aspect: str, path: Path) -> ImageResult:
        """One call, one image (or a refusal)."""
        images = [
            {
                "type": "image",
                "mime_type": mime_for(r),
                "data": base64.b64encode(r.read_bytes()).decode(),
            }
            for r in references
        ]
        body = {
            "model": self.model,
            "input": [{"type": "text", "text": prompt}, *images],
            "response_format": {
                "type": "image",
                "mime_type": "image/png",
                "aspect_ratio": nearest_aspect(aspect, ASPECTS),
                "image_size": self.image_size,
            },
        }
        headers = {"x-goog-api-key": require_key("GEMINI_API_KEY")}
        resp, seconds = timed(lambda: self._client.post(URL, json=body, headers=headers))
        if resp.status_code >= 400:
            raise ImageProviderError(f"gemini HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        image = find_image(data)
        base = {"provider": self.name, "model": self.model, "latency_s": seconds}
        if image is None:
            return ImageResult(**base, refused=True, refusal_reason=str(data)[:300])
        path.write_bytes(base64.b64decode(image["data"]))
        return ImageResult(**base, path=path, cost_usd=self.capabilities().usd_per_image)

    def generate(
        self,
        prompt: str,
        references: list[Path],
        aspect: str,
        n: int,
        seed: int | None,
        out: Path,
    ) -> list[ImageResult]:
        """``n`` calls; references beyond ``max_references`` are an error, not a silent cut."""
        if len(references) > self.capabilities().max_references:
            raise ImageProviderError(f"gemini takes at most 14 references, got {len(references)}")
        return [
            self._one(prompt, references, aspect, candidate_path(out, k)) for k in range(1, n + 1)
        ]

    def edit(self, image: Path, prompt: str, references: list[Path], out: Path) -> ImageResult:
        """Edit by sending the image first among the references."""
        return self._one(prompt, [image, *references], "16:9", candidate_path(out, 1))

    def upscale(self, image: Path, factor: int) -> Path:
        """Not offered; S9 upscales locally."""
        raise NotImplementedError("gemini adapter does not upscale (S9 does)")

    def capabilities(self) -> ProviderCapabilities:
        """Up to 14 references (Pro: 6 object + 5 character + 3 style) [VERIFY-4]."""
        return ProviderCapabilities(
            max_references=14,
            aspects=ASPECTS,
            max_px=4096,
            supports_edit=True,
            usd_per_image=float(os.environ.get("BOOKGEN_GEMINI_USD_PER_IMAGE", "0.134")),
        )
