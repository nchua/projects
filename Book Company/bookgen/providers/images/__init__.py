"""Image providers (SPEC §8.3, §8.6): the protocol, one adapter per module, a registry.

Seam: add a provider by writing ``<name>.py`` with a class implementing
``ImageProvider`` and adding it to ``PROVIDERS``. ``book bakeoff --providers``
and (session 4) S7 resolve names through ``get_provider``.
"""

from __future__ import annotations

from collections.abc import Callable

from bookgen.providers.images.base import (
    ImageProvider,
    ImageProviderError,
    ImageResult,
    ProviderCapabilities,
)
from bookgen.providers.images.fake import FakeImageProvider
from bookgen.providers.images.flux import FluxProvider
from bookgen.providers.images.gemini import GeminiProvider
from bookgen.providers.images.openai import OpenAIProvider

PROVIDERS: dict[str, Callable[[], ImageProvider]] = {
    "gemini": GeminiProvider,
    "flux": FluxProvider,
    "openai": OpenAIProvider,
    "fake": FakeImageProvider,
}
"""Provider name (as on the command line) to a zero-argument constructor."""


def get_provider(name: str) -> ImageProvider:
    """Build the named provider; unknown names list the known ones."""
    try:
        return PROVIDERS[name]()
    except KeyError:
        raise ImageProviderError(f"unknown provider {name!r}; known: {sorted(PROVIDERS)}") from None


__all__ = [
    "PROVIDERS",
    "ImageProvider",
    "ImageProviderError",
    "ImageResult",
    "ProviderCapabilities",
    "get_provider",
]
