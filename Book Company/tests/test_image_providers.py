"""Image adapters against a mock HTTP transport (no network): shapes, refusals, errors."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import httpx2
import pytest

from bookgen.providers.images import ImageProviderError, get_provider
from bookgen.providers.images.base import ImageProvider, nearest_aspect, size_for
from bookgen.providers.images.fake import FakeImageProvider, png_size, write_png
from bookgen.providers.images.flux import FluxProvider
from bookgen.providers.images.gemini import GeminiProvider
from bookgen.providers.images.openai import OpenAIProvider

PNG = b"\x89PNG\r\n\x1a\nfake"
B64 = base64.b64encode(PNG).decode()


@pytest.fixture(autouse=True)
def keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Placeholder keys so ``require_key`` passes; nothing leaves the process."""
    for var in ("GEMINI_API_KEY", "BFL_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.setenv(var, "test-key")


@pytest.fixture
def ref(tmp_path: Path) -> Path:
    """One reference image on disk."""
    return write_png(tmp_path / "maya_front.png", 4, 4, (1, 2, 3))


def _client(handler: Any) -> httpx2.Client:  # noqa: ANN401 - handler is a plain function
    """A client whose requests go to ``handler``."""
    return httpx2.Client(transport=httpx2.MockTransport(handler))


def test_registry_builds_every_provider_and_protocol_holds() -> None:
    """Each registered name builds an object satisfying ImageProvider."""
    for name in ("gemini", "flux", "openai", "fake"):
        assert isinstance(get_provider(name), ImageProvider)
    with pytest.raises(ImageProviderError, match="known"):
        get_provider("higgsfield")


def test_aspect_helpers() -> None:
    """A 2:1 spread maps to the nearest supported ratio; sizes round to 16."""
    assert nearest_aspect("2:1", ["1:1", "16:9", "21:9"]) == "16:9"
    w, h = size_for("2:1")
    assert w % 16 == 0 and h % 16 == 0 and 1.9 < w / h < 2.1


def test_gemini_request_and_image(tmp_path: Path, ref: Path) -> None:
    """Text then base64 images in ``input``; aspect snapped; image written per call."""
    seen: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(json.loads(request.content))
        assert request.headers["x-goog-api-key"] == "test-key"
        reply = {"steps": [{"type": "model_output", "content": [{"type": "image", "data": B64}]}]}
        return httpx2.Response(200, json=reply)

    results = GeminiProvider(_client(handler)).generate(
        "a kite", [ref], "2:1", 2, None, tmp_path / "out" / "s01"
    )
    assert [r.path.name for r in results if r.path] == ["s01_c1.png", "s01_c2.png"]
    assert results[0].path is not None and results[0].path.read_bytes() == PNG
    body = seen[0]
    assert body["input"][0] == {"type": "text", "text": "a kite"}
    assert body["input"][1]["type"] == "image" and body["input"][1]["mime_type"] == "image/png"
    assert body["response_format"]["aspect_ratio"] == "16:9" and len(seen) == 2


def test_gemini_no_image_is_a_refusal_and_http_error_raises(tmp_path: Path) -> None:
    """A 200 without an image is recorded as refused; a 500 raises."""
    blocked = _client(lambda r: httpx2.Response(200, json={"status": "blocked"}))
    [res] = GeminiProvider(blocked).generate("x", [], "1:1", 1, None, tmp_path / "s")
    assert res.refused and res.path is None and "blocked" in res.refusal_reason
    broken = _client(lambda r: httpx2.Response(500, text="boom"))
    with pytest.raises(ImageProviderError, match="HTTP 500"):
        GeminiProvider(broken).generate("x", [], "1:1", 1, None, tmp_path / "s")


def test_flux_submit_poll_download(tmp_path: Path, ref: Path) -> None:
    """Submit with input_image + size + seed, poll to Ready, download the sample."""
    polls = iter(
        [{"status": "Pending"}, {"status": "Ready", "result": {"sample": "https://cdn/x.png"}}]
    )
    sent: dict[str, Any] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.method == "POST":
            sent.update(json.loads(request.content))
            assert request.headers["x-key"] == "test-key"
            return httpx2.Response(
                200, json={"id": "1", "polling_url": "https://poll/1", "cost": 5}
            )
        if str(request.url).startswith("https://poll"):
            return httpx2.Response(200, json=next(polls))
        return httpx2.Response(200, content=PNG)

    flux = FluxProvider(_client(handler), sleep=lambda s: None)
    [res] = flux.generate("a kite", [ref], "2:1", 1, 42, tmp_path / "s01")
    assert res.path is not None and res.path.read_bytes() == PNG
    assert res.cost_usd == pytest.approx(0.05) and res.seed == 42
    assert sent["input_image"] and "input_image_2" not in sent and sent["seed"] == 42
    assert sent["width"] % 16 == 0 and sent["output_format"] == "png"


def test_flux_moderation_is_a_refusal(tmp_path: Path) -> None:
    """``Content Moderated`` becomes refused=True, not an exception."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.method == "POST":
            return httpx2.Response(200, json={"id": "1", "polling_url": "https://poll/1"})
        return httpx2.Response(200, json={"status": "Content Moderated"})

    [res] = FluxProvider(_client(handler), sleep=lambda s: None).generate(
        "x", [], "1:1", 1, None, tmp_path / "s"
    )
    assert res.refused and res.refusal_reason == "Content Moderated"


def test_openai_edits_multipart_and_moderation(tmp_path: Path, ref: Path) -> None:
    """References go as repeated image[] parts; moderation_blocked is a refusal for all n."""
    captured: dict[str, Any] = {}

    def ok(request: httpx2.Request) -> httpx2.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.content
        return httpx2.Response(200, json={"data": [{"b64_json": B64}, {"b64_json": B64}]})

    results = OpenAIProvider(_client(ok)).generate(
        "a kite", [ref, ref], "2:1", 2, None, tmp_path / "s"
    )
    assert captured["url"].endswith("/images/edits") and len(results) == 2
    assert captured["body"].count(b'name="image[]"') == 2
    assert b"gpt-image-2.5-sunburst" in captured["body"]

    def blocked(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(400, json={"error": {"code": "moderation_blocked"}})

    refused = OpenAIProvider(_client(blocked)).generate("x", [ref], "1:1", 3, None, tmp_path / "t")
    assert len(refused) == 3 and all(r.refused for r in refused)


def test_missing_key_is_a_clear_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No key: the error names the env var and no request is made."""
    monkeypatch.delenv("OPENAI_API_KEY")
    never = _client(lambda r: pytest.fail("no request without a key"))
    with pytest.raises(ImageProviderError, match="OPENAI_API_KEY"):
        OpenAIProvider(never).generate("x", [], "1:1", 1, None, tmp_path / "s")


def test_too_many_references_is_refused_before_calling(tmp_path: Path, ref: Path) -> None:
    """Exceeding max_references raises instead of silently dropping references."""
    never = _client(lambda r: pytest.fail("no request"))
    with pytest.raises(ImageProviderError, match="at most 8"):
        FluxProvider(never).generate("x", [ref] * 9, "1:1", 1, None, tmp_path / "s")


def test_fake_provider_writes_real_pngs(tmp_path: Path) -> None:
    """The fake writes decodable PNG headers at the aspect, and can refuse on a word."""
    fake = FakeImageProvider(refuse_when="scary")
    [res] = fake.generate("a kite", [], "2:1", 1, 7, tmp_path / "s01")
    assert res.path is not None and png_size(res.path)[0] > png_size(res.path)[1]
    assert fake.generate("a scary kite", [], "1:1", 2, None, tmp_path / "s02")[0].refused


def test_gemini_failed_status_raises_and_echoed_input_is_not_output(
    tmp_path: Path, ref: Path
) -> None:
    """Status failed is a platform error, not a refusal; an image in ``input`` isn't output."""
    failed = _client(lambda r: httpx2.Response(200, json={"status": "failed", "errors": ["x"]}))
    with pytest.raises(ImageProviderError, match="failed"):
        GeminiProvider(failed).generate("x", [], "1:1", 1, None, tmp_path / "s")
    echoed = {"status": "completed", "input": [{"type": "image", "data": B64}], "steps": []}
    [res] = GeminiProvider(_client(lambda r: httpx2.Response(200, json=echoed))).generate(
        "x", [ref], "1:1", 1, None, tmp_path / "t"
    )
    assert res.refused and res.path is None


def test_gemini_partial_failure_keeps_finished_candidates(tmp_path: Path) -> None:
    """Candidate 2 fails: the error carries candidate 1 (already paid for)."""
    replies = iter(
        [
            httpx2.Response(
                200,
                json={
                    "steps": [{"type": "model_output", "content": [{"type": "image", "data": B64}]}]
                },
            ),
            httpx2.Response(503, text="overloaded"),
        ]
    )
    with pytest.raises(ImageProviderError) as err:
        GeminiProvider(_client(lambda r: next(replies))).generate(
            "x", [], "1:1", 3, None, tmp_path / "s"
        )
    assert len(err.value.partial) == 1 and err.value.partial[0].path is not None


def test_flux_without_cost_field_bills_list_price_and_bad_download_raises(tmp_path: Path) -> None:
    """No ``cost`` in the reply: list price, so the cap still sees spend. Expired URL: error."""
    status = {"code": 200}

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.method == "POST":
            return httpx2.Response(200, json={"id": "1", "polling_url": "https://poll/1"})
        if str(request.url).startswith("https://poll"):
            return httpx2.Response(
                200, json={"status": "Ready", "result": {"sample": "https://cdn/x"}}
            )
        return httpx2.Response(status["code"], content=PNG)

    flux = FluxProvider(_client(handler), sleep=lambda s: None)
    [res] = flux.generate("x", [], "1:1", 1, None, tmp_path / "s")
    assert res.cost_usd == pytest.approx(flux.capabilities().usd_per_image)
    status["code"] = 403
    with pytest.raises(ImageProviderError, match="download HTTP 403"):
        flux.generate("x", [], "1:1", 1, None, tmp_path / "t")


def test_transport_errors_become_provider_errors(tmp_path: Path) -> None:
    """A timeout or connection error is an ImageProviderError the bake-off can record."""

    def boom(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectTimeout("timed out", request=request)

    with pytest.raises(ImageProviderError, match="ConnectTimeout"):
        OpenAIProvider(_client(boom)).generate("x", [], "1:1", 1, None, tmp_path / "s")


def test_openai_latency_is_per_image_and_short_reply_is_partial(tmp_path: Path) -> None:
    """Latency divided by n; fewer images than asked raises with the ones received."""
    one = _client(lambda r: httpx2.Response(200, json={"data": [{"b64_json": B64}]}))
    with pytest.raises(ImageProviderError, match="1 of 2") as err:
        OpenAIProvider(one).generate("x", [], "1:1", 2, None, tmp_path / "s")
    assert len(err.value.partial) == 1


def test_edit_keeps_the_input_aspect(tmp_path: Path) -> None:
    """Editing a square page asks for a square, not a hard-coded 16:9."""
    page = write_png(tmp_path / "page.png", 64, 64, (5, 5, 5))
    fake = FakeImageProvider()
    fake.edit(page, "fix the hand", [], tmp_path / "e")
    assert fake.calls[-1]["aspect"] == "64:64"
