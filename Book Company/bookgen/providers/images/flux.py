"""Black Forest Labs FLUX.2 via the BFL REST API (§8.3).

Shape per docs.bfl.ai (read 2026-11-01): POST ``/v1/<model>`` with ``x-key``;
body ``prompt``, ``input_image`` .. ``input_image_8``, ``width``, ``height``,
``seed``, ``output_format``, ``safety_tolerance``; the reply has ``polling_url``
(and ``cost`` in credits). Poll until ``status`` is terminal; ``Ready`` carries
a signed ``result.sample`` URL valid for 10 minutes. ``Request Moderated`` /
``Content Moderated`` are refusals. Reference images are sent as base64 strings;
the docs show URLs only, so that is ``[VERIFY-4]`` on the first live call.
"""

from __future__ import annotations

import base64
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
    candidate_path,
    require_key,
    size_for,
    timed,
)

BASE = "https://api.bfl.ai/v1"
MODERATED = {"Request Moderated", "Content Moderated"}
FAILED = {"Error", "Failed", "Task not found", "No Card Generated"}
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

    def _poll(self, url: str, headers: dict[str, str]) -> dict[str, Any]:
        """GET ``url`` until a terminal status; returns the final body."""
        for _ in range(self._poll_limit):
            body: dict[str, Any] = self._client.get(url, headers=headers).json()
            if body.get("status") not in {"Pending", "Reasoning", "Generating", None}:
                return body
            self._sleep(0.5)
        raise ImageProviderError("flux: polling timed out")

    def _one(
        self, prompt: str, references: list[Path], aspect: str, seed: int | None, path: Path
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
        for i, ref in enumerate(references, start=1):
            body["input_image" if i == 1 else f"input_image_{i}"] = base64.b64encode(
                ref.read_bytes()
            ).decode()
        headers = {"x-key": require_key("BFL_API_KEY"), "accept": "application/json"}

        def submit_and_wait() -> tuple[dict[str, Any], dict[str, Any]]:
            resp = self._client.post(f"{BASE}/{self.model}", json=body, headers=headers)
            if resp.status_code >= 400:
                raise ImageProviderError(f"flux HTTP {resp.status_code}: {resp.text[:300]}")
            submitted: dict[str, Any] = resp.json()
            return submitted, self._poll(submitted["polling_url"], headers)

        (submitted, final), seconds = timed(submit_and_wait)
        cost = float(submitted.get("cost") or 0) * USD_PER_CREDIT
        base = {"provider": self.name, "model": self.model, "seed": seed, "latency_s": seconds}
        status = final.get("status")
        if status in MODERATED:
            return ImageResult(**base, cost_usd=cost, refused=True, refusal_reason=str(status))
        if status != "Ready":
            raise ImageProviderError(f"flux: status {status!r}: {str(final)[:300]}")
        sample = (final.get("result") or {}).get("sample")
        if not sample:
            raise ImageProviderError("flux: Ready without result.sample")
        path.write_bytes(self._client.get(sample).content)
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
        if len(references) > self.capabilities().max_references:
            raise ImageProviderError(f"flux takes at most 8 references, got {len(references)}")
        return [
            self._one(
                prompt,
                references,
                aspect,
                None if seed is None else seed + k - 1,
                candidate_path(out, k),
            )
            for k in range(1, n + 1)
        ]

    def edit(self, image: Path, prompt: str, references: list[Path], out: Path) -> ImageResult:
        """Edit with the image as ``input_image``."""
        return self._one(prompt, [image, *references], "16:9", None, candidate_path(out, 1))

    def upscale(self, image: Path, factor: int) -> Path:
        """Not offered; S9 upscales locally."""
        raise NotImplementedError("flux adapter does not upscale (S9 does)")

    def capabilities(self) -> ProviderCapabilities:
        """8 references via API, up to 4 MP output [VERIFY-4]."""
        return ProviderCapabilities(
            max_references=8,
            aspects=["1:1", "4:3", "3:2", "16:9", "2:1", "21:9"],
            max_px=2048,
            supports_edit=True,
            usd_per_image=float(os.environ.get("BOOKGEN_FLUX_USD_PER_IMAGE", "0.06")),
        )
