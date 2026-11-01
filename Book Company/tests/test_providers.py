"""Provider stubs: LLM roles (§8.4) and the image protocol (§8.6)."""

from __future__ import annotations

from bookgen.providers.images import ImageProvider
from bookgen.providers.llm import Role, model_for


def test_writer_and_judge_differ() -> None:
    """The writer is Opus 5.5 and the judge Sonnet 5.5, never the same (§6.2)."""
    assert model_for(Role.WRITER) == "claude-opus-5-5"
    assert model_for(Role.JUDGE) == "claude-sonnet-5-5"


def test_image_protocol_shape() -> None:
    """The protocol exposes the four §8.6 methods."""
    for name in ("generate", "edit", "upscale", "capabilities"):
        assert callable(getattr(ImageProvider, name))
