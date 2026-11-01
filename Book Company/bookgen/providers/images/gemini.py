"""Google Gemini image models ("Nano Banana Pro") via the Interactions REST API (§8.3).

Request shape per ai.google.dev/gemini-api/docs/image-generation (read 2026-11-01):
POST ``/v1beta/interactions`` with ``x-goog-api-key``; ``input`` is a text item plus
base64 image items; ``response_format`` sets ``aspect_ratio`` and ``image_size``.
One image per call, so ``n`` candidates are ``n`` calls. No seed parameter.

Outcome rules (the docs give no raw response schema, so ``[VERIFY-2]`` on the first
live call): the image is looked for only in ``steps[]`` of type ``model_output`` (or
a top-level ``output_image``), never anywhere else, so an echoed ``input`` can't be
mistaken for output. ``status`` failed/incomplete or a non-empty ``errors`` is a
platform failure (raised); a completed interaction with no image is a refusal.
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
    aspect_of,
    candidate_path,
    check_reference_count,
    each_candidate,
    guarded,
    mime_for,
    nearest_aspect,
    require_key,
    timed,
)

URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
ASPECTS = ["1:1", "3:2", "2:3", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]
"""Listed on the docs page; per-model support isn't broken down there [VERIFY-4]."""

FAILED_STATUSES = {"failed", "incomplete", "cancelled"}


def output_image(body: dict[str, Any]) -> dict[str, Any] | None:
    """The last image block the model produced, or ``None``."""
    found = None
    for step in body.get("steps") or []:
        if step.get("type") != "model_output":
            continue
        for block in step.get("content") or []:
            if block.get("type") == "image" and block.get("data"):
                found = block
    top = body.get("output_image")
    if found is None and isinstance(top, dict) and top.get("data"):
        found = top
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
        sent_aspect = nearest_aspect(aspect, ASPECTS)
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
                "aspect_ratio": sent_aspect,
                "image_size": self.image_size,
            },
        }
        headers = {"x-goog-api-key": require_key("GEMINI_API_KEY")}
        resp, seconds = timed(
            lambda: guarded(self.name, lambda: self._client.post(URL, json=body, headers=headers))
        )
        if resp.status_code >= 400:
            raise ImageProviderError(f"gemini HTTP {resp.status_code}: {resp.text[:300]}")
        data: dict[str, Any] = guarded(self.name, resp.json)
        if data.get("status") in FAILED_STATUSES or data.get("errors"):
            raise ImageProviderError(
                f"gemini {data.get('status')}: {str(data.get('errors'))[:300]}"
            )
        base = {
            "provider": self.name,
            "model": self.model,
            "latency_s": seconds,
            "aspect": sent_aspect,
        }
        image = output_image(data)
        if image is None:
            reason = f"status {data.get('status')!r}, no image in model output"
            return ImageResult(**base, refused=True, refusal_reason=reason)
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
        """``n`` calls; a failure part-way raises with the finished candidates attached."""
        check_reference_count(self, references)
        return each_candidate(
            n, lambda k: self._one(prompt, references, aspect, candidate_path(out, k))
        )

    def edit(self, image: Path, prompt: str, references: list[Path], out: Path) -> ImageResult:
        """Edit by sending the image first among the references, keeping its aspect."""
        return self._one(prompt, [image, *references], aspect_of(image), candidate_path(out, 1))

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
