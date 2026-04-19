"""Tests for detect_media_type_from_bytes — guards against the filename-vs-bytes
mismatch that broke screenshot processing (Claude 400'd on PNG bytes declared
as image/jpeg).
"""
import pytest

from app.services.screenshot_service import detect_media_type_from_bytes


PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG_MAGIC = b"\xff\xd8\xff\xe0" + b"\x00" * 16
GIF87A_MAGIC = b"GIF87a" + b"\x00" * 16
GIF89A_MAGIC = b"GIF89a" + b"\x00" * 16
WEBP_MAGIC = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 16
HEIC_MAGIC = b"\x00\x00\x00\x20" + b"ftyp" + b"heic" + b"\x00" * 16


def test_detects_png():
    assert detect_media_type_from_bytes(PNG_MAGIC) == "image/png"


def test_detects_jpeg():
    assert detect_media_type_from_bytes(JPEG_MAGIC) == "image/jpeg"


def test_detects_gif87():
    assert detect_media_type_from_bytes(GIF87A_MAGIC) == "image/gif"


def test_detects_gif89():
    assert detect_media_type_from_bytes(GIF89A_MAGIC) == "image/gif"


def test_detects_webp():
    assert detect_media_type_from_bytes(WEBP_MAGIC) == "image/webp"


def test_heic_raises_clear_error():
    with pytest.raises(ValueError, match="HEIC"):
        detect_media_type_from_bytes(HEIC_MAGIC)


def test_unknown_format_raises():
    with pytest.raises(ValueError, match="Unrecognized"):
        detect_media_type_from_bytes(b"not an image at all!!!!")


def test_too_short_raises():
    with pytest.raises(ValueError, match="too short"):
        detect_media_type_from_bytes(b"\x89PNG")


def test_filename_lies_png_bytes_detected():
    # Regression: iOS used to upload PNG bytes with filename=foo.jpg. The
    # bytes are authoritative — we ignore the filename entirely.
    assert detect_media_type_from_bytes(PNG_MAGIC) == "image/png"


# --- Activity prefix stripping (Apple Watch labels) ---------------------------

from app.services.screenshot_service import _strip_activity_prefix  # noqa: E402


@pytest.mark.parametrize("raw,expected", [
    ("Indoor Run", "Run"),
    ("Outdoor Run", "Run"),
    ("Indoor Cycle", "Cycle"),
    ("Outdoor Cycling", "Cycling"),
    ("Pool Swim", "Swim"),
    ("Open Water Swim", "Swim"),
    ("Indoor Walk", "Walk"),
    ("Pickleball", "Pickleball"),  # No prefix — left alone
    ("Tennis", "Tennis"),
    ("  Outdoor  Run  ", "Run"),  # Leading/trailing whitespace
    ("INDOOR RUN", "RUN"),         # Case-insensitive prefix match, preserves case
])
def test_strip_activity_prefix(raw, expected):
    assert _strip_activity_prefix(raw) == expected
