"""OpenAI GPT Image via the Images REST API (§8.3).

Shape per developers.openai.com/api/docs/guides/image-generation (read 2026-11-01):
with references, POST ``/v1/images/edits`` as multipart with repeated ``image[]``
files; without, POST ``/v1/images/generations``. ``size`` is ``WxH`` (multiples
of 16, ratio between 1:3 and 3:1); results are ``data[].b64_json``. A blocked
request is HTTP 400 with ``error.code == "moderation_blocked"``: a refusal.
No seed parameter. One request returns all ``n``, so per-image latency is the
call's time divided by ``n`` (comparable with one-call-per-image providers).
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

import httpx2

from bookgen.providers.images.base import (
    ImageProviderError,
    ImageResult,
    ProviderCapabilities,
    aspect_of,
    candidate_path,
    check_reference_count,
    guarded,
    mime_for,
    require_key,
    size_for,
    timed,
)

BASE = "https://api.openai.com/v1/images"


class OpenAIProvider:
    """``ImageProvider`` for GPT Image; key from ``OPENAI_API_KEY``."""

    name = "openai"

    def __init__(self, client: httpx2.Client | None = None, model: str | None = None) -> None:
        """Use ``client`` (tests pass a mock transport) and ``model`` or the env default."""
        self.model = model or os.environ.get("BOOKGEN_OPENAI_IMAGE_MODEL", "gpt-image-2.5-sunburst")
        self.quality = os.environ.get("BOOKGEN_OPENAI_IMAGE_QUALITY", "high")
        self._client = client or httpx2.Client(timeout=300)

    def generate(
        self,
        prompt: str,
        references: list[Path],
        aspect: str,
        n: int,
        seed: int | None,
        out: Path,
    ) -> list[ImageResult]:
        """One request for all ``n`` candidates (the API's ``n``)."""
        check_reference_count(self, references)
        width, height = size_for(aspect)
        headers = {"Authorization": f"Bearer {require_key('OPENAI_API_KEY')}"}
        fields = {
            "model": self.model,
            "prompt": prompt,
            "size": f"{width}x{height}",
            "quality": self.quality,
        }

        def call() -> httpx2.Response:
            if not references:
                return self._client.post(
                    f"{BASE}/generations", json=fields | {"n": n}, headers=headers
                )
            files = [("image[]", (r.name, r.read_bytes(), mime_for(r))) for r in references]
            return self._client.post(
                f"{BASE}/edits", data=fields | {"n": str(n)}, files=files, headers=headers
            )

        resp, seconds = timed(lambda: guarded(self.name, call))
        base = {
            "provider": self.name,
            "model": self.model,
            "latency_s": seconds / max(n, 1),
            "aspect": f"{width}:{height}",
        }
        if resp.status_code == 400 and _code(resp) == "moderation_blocked":
            reason = resp.text[:300]
            return [ImageResult(**base, refused=True, refusal_reason=reason) for _ in range(n)]
        if resp.status_code >= 400:
            raise ImageProviderError(f"openai HTTP {resp.status_code}: {resp.text[:300]}")
        data = guarded(self.name, lambda: resp.json()["data"])
        results = []
        for k, item in enumerate(data, start=1):
            path = candidate_path(out, k)
            path.write_bytes(base64.b64decode(item["b64_json"]))
            results.append(
                ImageResult(**base, path=path, cost_usd=self.capabilities().usd_per_image)
            )
        if len(results) != n:
            raise ImageProviderError(
                f"openai returned {len(results)} of {n} images", partial=results
            )
        return results

    def edit(self, image: Path, prompt: str, references: list[Path], out: Path) -> ImageResult:
        """Edit with the image first among the references, keeping its aspect."""
        return self.generate(prompt, [image, *references], aspect_of(image), 1, None, out)[0]

    def upscale(self, image: Path, factor: int) -> Path:
        """Not offered; S9 upscales locally."""
        raise NotImplementedError("openai adapter does not upscale (S9 does)")

    def capabilities(self) -> ProviderCapabilities:
        """Any WxH within the documented limits; reference cap not documented [VERIFY-4]."""
        return ProviderCapabilities(
            max_references=16,
            aspects=["1:1", "4:3", "3:2", "16:9", "2:1", "21:9"],
            max_px=3840,
            supports_edit=True,
            usd_per_image=float(os.environ.get("BOOKGEN_OPENAI_USD_PER_IMAGE", "0.20")),
        )


def _code(resp: httpx2.Response) -> str | None:
    """``error.code`` from an error body, if it parses."""
    try:
        return (resp.json().get("error") or {}).get("code")
    except ValueError:
        return None
