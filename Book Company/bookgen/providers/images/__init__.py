"""Image provider protocol and (from session 3) one adapter module per provider (SPEC §8.3)."""

from bookgen.providers.images.base import ImageProvider, ImageResult, ProviderCapabilities

__all__ = ["ImageProvider", "ImageResult", "ProviderCapabilities"]
