"""The real provider's bookkeeping, against a stub client (no network)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from bookgen.models import StageId
from bookgen.prompts import load_prompt
from bookgen.providers.llm import (
    FALLBACK_BETA,
    AnthropicProvider,
    Budget,
    CostCapExceeded,
    LLMOutputError,
    LLMRefusal,
    Role,
    price,
)


class Answer(BaseModel):
    """A tiny structured output."""

    word: str


class _Raw:
    """Mimics the SDK's raw response: the body via ``json()``."""

    def __init__(self, body: dict[str, Any]) -> None:
        self.body = body

    def json(self) -> dict[str, Any]:
        """The response body."""
        return self.body


class StubClient:
    """Returns queued response bodies and records the request kwargs."""

    def __init__(self, bodies: list[dict[str, Any]]) -> None:
        self.bodies, self.requests = bodies, []
        self.beta = SimpleNamespace(
            messages=SimpleNamespace(with_raw_response=SimpleNamespace(create=self._create))
        )

    def _create(self, **kw: Any) -> _Raw:  # noqa: ANN401
        """Record the request, return the next body."""
        self.requests.append(kw)
        return _Raw(self.bodies.pop(0))


def _body(text: str | None, stop: str = "end_turn", model: str = "claude-opus-5-5") -> dict:
    """A Messages API response body."""
    content = [{"type": "text", "text": text}] if text is not None else []
    usage = {
        "input_tokens": 1000,
        "output_tokens": 500,
        "cache_creation_input_tokens": 2000,
        "cache_read_input_tokens": 0,
    }
    return {"id": "msg_1", "model": model, "stop_reason": stop, "content": content, "usage": usage}


def _call(client: StubClient, tmp_path: Path, budget: Budget | None = None) -> Answer:
    """One writer call through a fresh session."""
    session = AnthropicProvider(client, budget).session(StageId.S4, tmp_path / "logs")  # type: ignore[arg-type]
    return session.structured(
        role=Role.WRITER,
        label="plan",
        prompt=load_prompt("plan"),
        context=["GUIDE", "BIBLE"],
        user="inputs",
        schema=Answer,
    )


def test_price_uses_cache_rates() -> None:
    """Opus 5.5: $4 in, $20 out, $5 cache write, $0.20 cache read per MTok."""
    usage = {"input_tokens": 1_000_000, "output_tokens": 0, "cache_read_input_tokens": 1_000_000}
    assert price("claude-opus-5-5", usage) == pytest.approx(4.20)
    assert price("unknown-model", {"output_tokens": 1_000_000}) == pytest.approx(25.0)


def test_request_shape_logging_and_cost(tmp_path: Path) -> None:
    """Context first and cached, fallback opt-in, one log file with hash and cost."""
    client = StubClient([_body('{"word": "toast"}')])
    assert _call(client, tmp_path).word == "toast"
    req = client.requests[0]
    assert [b["text"] for b in req["system"]][:2] == ["GUIDE", "BIBLE"]
    assert all("cache_control" in b for b in req["system"][:2])
    assert "cache_control" not in req["system"][2]
    assert req["fallbacks"] == "default" and req["betas"] == [FALLBACK_BETA]
    assert req["output_config"]["format"]["type"] == "json_schema"
    assert req["model"] == "claude-opus-5-5"
    [log] = list((tmp_path / "logs").glob("S4-plan-*.json"))
    record = json.loads(log.read_text())
    expected = (1000 * 4 + 500 * 20 + 2000 * 5) / 1e6
    assert record["cost_usd"] == pytest.approx(expected)
    assert record["prompt"]["name"] == "plan" and len(record["prompt_hash"]) == 64


def test_invalid_output_retries_once_then_fails(tmp_path: Path) -> None:
    """Invalid JSON gets one corrective retry carrying the error; a second failure raises."""
    client = StubClient([_body('{"wrong": 1}'), _body('{"word": "ok"}')])
    assert _call(client, tmp_path).word == "ok"
    assert "did not pass validation" in client.requests[1]["messages"][0]["content"]
    client = StubClient([_body('{"wrong": 1}'), _body('{"wrong": 2}')])
    with pytest.raises(LLMOutputError):
        _call(client, tmp_path)


def test_refusal_and_truncation_raise(tmp_path: Path) -> None:
    """A refusal after the server-side fallback, or a max_tokens cut, is not retried."""
    with pytest.raises(LLMRefusal):
        _call(StubClient([_body(None, stop="refusal")]), tmp_path)
    with pytest.raises(LLMOutputError, match="truncated"):
        _call(StubClient([_body('{"wo', stop="max_tokens")]), tmp_path)


def test_cost_cap_refuses_before_calling(tmp_path: Path) -> None:
    """A call whose worst case breaks BOOKGEN_MAX_COST_USD is never sent."""
    client = StubClient([_body('{"word": "x"}')])
    with pytest.raises(CostCapExceeded):
        _call(client, tmp_path, Budget(cap_usd=0.10))
    assert client.requests == []


def test_budget_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The cap defaults to $5 and comes from BOOKGEN_MAX_COST_USD."""
    monkeypatch.delenv("BOOKGEN_MAX_COST_USD", raising=False)
    assert Budget().cap_usd == 5.0
    monkeypatch.setenv("BOOKGEN_MAX_COST_USD", "1.5")
    assert Budget().cap_usd == 1.5


def test_fallback_response_uses_final_text_and_bills_every_attempt(tmp_path: Path) -> None:
    """A mid-output decline: the partial text is ignored and both attempts are costed."""
    body = _body(None, model="claude-opus-5")
    body["content"] = [
        {"type": "text", "text": '{"wo'},
        {
            "type": "fallback",
            "from": {"model": "claude-opus-5-5"},
            "to": {"model": "claude-opus-5"},
        },
        {"type": "text", "text": '{"word": "saved"}'},
    ]
    body["usage"]["iterations"] = [
        {"type": "message", "input_tokens": 1000, "output_tokens": 100},
        {"type": "fallback_message", "input_tokens": 1000, "output_tokens": 500},
    ]
    client = StubClient([body])
    assert _call(client, tmp_path).word == "saved"
    [log] = list((tmp_path / "logs").glob("*.json"))
    expected = (1000 * 4 + 100 * 20) / 1e6 + (1000 * 5 + 500 * 25) / 1e6
    assert json.loads(log.read_text())["cost_usd"] == pytest.approx(expected)


def test_bad_cap_setting_is_a_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A malformed BOOKGEN_MAX_COST_USD is reported, not a bare ValueError traceback."""
    from bookgen.providers.llm import ConfigError

    monkeypatch.setenv("BOOKGEN_MAX_COST_USD", "five")
    with pytest.raises(ConfigError, match="must be a number"):
        Budget()


def test_images_go_before_the_text_and_large_ones_are_shrunk(tmp_path: Path) -> None:
    """Vision calls: base64 image blocks then the text; a big PNG becomes a <=1568px JPEG."""
    import base64 as b64
    import io

    from PIL import Image

    from bookgen.providers.images.fake import write_png
    from bookgen.providers.llm import MAX_IMAGE_EDGE, encode_image, user_content

    small = write_png(tmp_path / "small.png", 10, 10, (1, 2, 3))
    big = write_png(tmp_path / "big.png", 3000, 1500, (1, 2, 3))
    content = user_content("score it", [small, big])
    assert isinstance(content, list) and [b["type"] for b in content] == ["image", "image", "text"]
    assert content[0]["source"]["media_type"] == "image/png"
    media, data = encode_image(big)
    assert media == "image/jpeg"
    with Image.open(io.BytesIO(b64.b64decode(data))) as im:
        assert max(im.size) == MAX_IMAGE_EDGE
