"""Black Forest Labs FLUX.2 via the BFL REST API (§8.3).

Shape per docs.bfl.ai (read 2026-11-01): POST ``/v1/<model>`` with ``x-key``;
body ``prompt``, ``input_image`` .. ``input_image_8``, ``width``, ``height``,
``seed``, ``output_format``, ``safety_tolerance``; the reply has ``polling_url``.
Poll until ``status`` is terminal; ``Ready`` carries a signed ``result.sample`` URL
valid for 10 minutes. ``Request Moderated`` / ``Content Moderated`` are refusals.
Reference images are sent as base64 strings; the docs show URLs only, so that is
``[VERIFY-4]`` on the first live call. Cost: the reply's ``cost`` (credits) when
present, else the list price, so spend always counts toward the bake-off cap.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2

from bookgen.providers.images.base import (
    ImageProviderError,
    ImageResult,
    ProviderCapabilities,
    aspect_of,
    b64_file,
    candidate_path,
    check_reference_count,
    each_candidate,
    guarded,
    raise_for_status,
    require_key,
    size_for,
    timed_call,
)

BASE = "https://api.bfl.ai/v1"
PENDING = {"Pending", "Reasoning", "Generating", None}
MODERATED = {"Request Moderated", "Content Moderated"}
USD_PER_CREDIT = 0.01
"""BFL bills in credits; $0.01 per credit at list price [VERIFY-4]."""


class FluxProvider:
    """``ImageProvider`` for FLUX.2; key from ``BFL_API_KEY``."""

    name = "flux"

    def __init__(
        self,
        client: httpx2.Client | None = None,
        model: str | None = None,
        sleep: Callable[[float], None] = time.sleep,
        poll_limit: int = 600,
    ) -> None:
        """Use ``client``/``sleep`` (tests inject both); poll at most ``poll_limit`` times."""
        self.model = model or os.environ.get("BOOKGEN_FLUX_MODEL", "flux-2-pro")
        self._client = client or httpx2.Client(timeout=120)
        self._sleep = sleep
        self._poll_limit = poll_limit
        self._caps = ProviderCapabilities(
            max_references=8,  # via API; up to 4 MP output [VERIFY-4]
            aspects=["1:1", "4:3", "3:2", "16:9", "2:1", "21:9"],
            max_px=2048,
            supports_edit=True,
            usd_per_image=float(os.environ.get("BOOKGEN_FLUX_USD_PER_IMAGE", "0.06")),
        )

    def _poll(self, url: str, headers: dict[str, str]) -> dict[str, Any]:
        """GET ``url`` until a terminal status; returns the final body."""
        for _ in range(self._poll_limit):
            body: dict[str, Any] = self._client.get(url, headers=headers).json()
            if body.get("status") not in PENDING:
                return body
            self._sleep(0.5)
        raise ImageProviderError("flux: polling timed out")

    def _one(
        self, prompt: str, images: list[str], aspect: str, seed: int | None, path: Path
    ) -> ImageResult:
        """Submit, poll, download one image (or record a moderation refusal)."""
        width, height = size_for(aspect)
        body: dict[str, Any] = {
            "prompt": prompt,
            "width": width,
            "height": height,
            "output_format": "png",
        }
        if seed is not None:
            body["seed"] = seed
        for i, data in enumerate(images, start=1):
            body["input_image" if i == 1 else f"input_image_{i}"] = data
        headers = {"x-key": require_key("BFL_API_KEY"), "accept": "application/json"}

        def submit_and_wait() -> tuple[dict[str, Any], dict[str, Any]]:
            resp = self._client.post(f"{BASE}/{self.model}", json=body, headers=headers)
            raise_for_status(self.name, resp)
            submitted: dict[str, Any] = resp.json()
            return submitted, self._poll(submitted["polling_url"], headers)

        (submitted, final), seconds = timed_call(self.name, submit_and_wait)
        credits = submitted.get("cost") or final.get("cost")
        cost = float(credits) * USD_PER_CREDIT if credits else self._caps.usd_per_image
        base = {
            "provider": self.name,
            "model": self.model,
            "seed": seed,
            "latency_s": seconds,
            "aspect": f"{width}:{height}",
        }
        status = final.get("status")
        if status in MODERATED:
            return ImageResult(**base, cost_usd=cost, refused=True, refusal_reason=str(status))
        sample = (final.get("result") or {}).get("sample")
        if status != "Ready" or not sample:
            raise ImageProviderError(f"flux: status {status!r}: {str(final)[:300]}")
        download = guarded(self.name, lambda: self._client.get(sample))
        raise_for_status(self.name, download, "download HTTP")  # 403 = signed URL expired
        path.write_bytes(download.content)
        return ImageResult(**base, path=path, cost_usd=cost)

    def generate(
        self,
        prompt: str,
        references: list[Path],
        aspect: str,
        n: int,
        seed: int | None,
        out: Path,
    ) -> list[ImageResult]:
        """``n`` submissions; seeds step by one so candidates differ but replay."""
        check_reference_count(self, references)
        images = [b64_file(r) for r in references]
        return each_candidate(
            n,
            lambda k: self._one(
                prompt,
                images,
                aspect,
                None if seed is None else seed + k - 1,
                candidate_path(out, k),
            ),
        )

    def edit(self, image: Path, prompt: str, references: list[Path], out: Path) -> ImageResult:
        """Edit with the image as ``input_image``, keeping its aspect."""
        images = [b64_file(r) for r in [image, *references]]
        return self._one(prompt, images, aspect_of(image), None, candidate_path(out, 1))

    def upscale(self, image: Path, factor: int) -> Path:
        """Not offered; S9 upscales locally."""
        raise NotImplementedError("flux adapter does not upscale (S9 does)")

    def capabilities(self) -> ProviderCapabilities:
        """Reference cap, aspects, size and list price (built once)."""
        return self._caps
