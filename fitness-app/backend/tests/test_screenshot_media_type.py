"""Tests for detect_media_type_from_bytes — guards against the filename-vs-bytes
mismatch that broke screenshot processing (Claude 400'd on PNG bytes declared
as image/jpeg). The bytes are authoritative — the filename never enters the
function.
"""
import pytest

from app.services.screenshot_service import _strip_activity_prefix, detect_media_type_from_bytes

PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG_MAGIC = b"\xff\xd8\xff\xe0" + b"\x00" * 16
GIF87A_MAGIC = b"GIF87a" + b"\x00" * 16
GIF89A_MAGIC = b"GIF89a" + b"\x00" * 16
WEBP_MAGIC = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 16
HEIC_MAGIC = b"\x00\x00\x00\x20" + b"ftyp" + b"heic" + b"\x00" * 16


@pytest.mark.parametrize("magic_bytes,expected_type", [
    pytest.param(PNG_MAGIC, "image/png", id="png"),
    pytest.param(JPEG_MAGIC, "image/jpeg", id="jpeg"),
    pytest.param(GIF87A_MAGIC, "image/gif", id="gif87a"),
    pytest.param(GIF89A_MAGIC, "image/gif", id="gif89a"),
    pytest.param(WEBP_MAGIC, "image/webp", id="webp"),
])
def test_detects_media_type_from_magic_bytes(magic_bytes, expected_type):
    assert detect_media_type_from_bytes(magic_bytes) == expected_type


@pytest.mark.parametrize("data,error_match", [
    pytest.param(HEIC_MAGIC, "HEIC", id="heic"),
    pytest.param(b"not an image at all!!!!", "Unrecognized", id="unknown-format"),
    pytest.param(b"\x89PNG", "too short", id="too-short"),
])
def test_unsupported_bytes_raise_clear_error(data, error_match):
    with pytest.raises(ValueError, match=error_match):
        detect_media_type_from_bytes(data)


# --- Activity prefix stripping (Apple Watch labels) ---------------------------

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
