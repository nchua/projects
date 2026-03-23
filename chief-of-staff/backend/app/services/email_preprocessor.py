"""Email preprocessing for data minimization before AI extraction.

Ported from prompt-harness/prompts.py — the battle-tested versions
with precompiled regexes and smarter word-boundary truncation.

Per spec: Strip email signatures, quoted replies, marketing content,
and HTML tags before sending to Claude. Reduces cost and data exposure.
"""

import hashlib
import re
from html.parser import HTMLParser


# =============================================================================
# PRECOMPILED REGEX PATTERNS
# =============================================================================

_RE_HTML_TAGS = re.compile(r"<[^>]+>")
_RE_QUOTED_REPLY = re.compile(r"^On\s.+wrote:\s*$")
_RE_SIG_PATTERNS = [
    re.compile(r"\n--\s*\n.*", re.DOTALL | re.IGNORECASE),
    re.compile(
        r"\nSent from my (?:iPhone|iPad|Galaxy|Pixel).*",
        re.DOTALL | re.IGNORECASE,
    ),
    re.compile(
        r"\nGet Outlook for (?:iOS|Android).*",
        re.DOTALL | re.IGNORECASE,
    ),
]
_RE_FOOTER_PATTERNS = [
    re.compile(r"\n.*[Uu]nsubscribe.*", re.DOTALL),
    re.compile(r"\n.*[Yy]ou(?:'re| are) receiving this.*", re.DOTALL),
    re.compile(
        r"\n.*[Mm]anage (?:your )?(?:preferences|subscription).*",
        re.DOTALL,
    ),
    re.compile(
        r"\n.*[Cc]lick here to (?:unsubscribe|opt.out).*", re.DOTALL
    ),
]
_RE_BLANK_LINES = re.compile(r"\n{3,}")

# Max chars to send to the AI extraction pipeline
MAX_BODY_CHARS = 8000
MIN_BODY_CHARS = 50


# =============================================================================
# HTML-TO-TEXT
# =============================================================================


class _HTMLTextExtractor(HTMLParser):
    """Strips HTML tags and extracts plain text."""

    BLOCK_TAGS = {
        "p", "div", "br", "li",
        "h1", "h2", "h3", "h4", "h5", "h6", "tr",
    }
    SKIP_TAGS = {"script", "style"}

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag.lower() in self.SKIP_TAGS:
            self._skip = True
        if tag.lower() in self.BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.SKIP_TAGS:
            self._skip = False
        if tag.lower() in self.BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts).strip()


def html_to_text(html: str) -> str:
    """Convert HTML to plain text, stripping scripts and styles."""
    parser = _HTMLTextExtractor()
    parser.feed(html)
    return parser.get_text()


# =============================================================================
# PREPROCESSING FUNCTIONS
# =============================================================================


def strip_email_noise(raw_text: str | None) -> str:
    """Remove signatures, quoted replies, marketing footers, HTML tags.

    This is the data minimization step — we send only the useful
    content to Claude, reducing cost and data exposure.
    """
    if not raw_text:
        return ""

    text = raw_text

    # Strip HTML tags
    text = _RE_HTML_TAGS.sub("", text)
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&nbsp;", " ")
        .replace("&quot;", '"')
    )

    # Strip quoted replies line-by-line
    lines = text.split("\n")
    cleaned_lines: list[str] = []
    in_quote = False
    for line in lines:
        stripped = line.strip()
        if _RE_QUOTED_REPLY.match(stripped):
            in_quote = True
            continue
        if stripped.startswith("-----Original Message-----"):
            in_quote = True
            continue
        if stripped.startswith("---------- Forwarded message"):
            in_quote = True
            continue
        if stripped.startswith(">"):
            continue
        if in_quote:
            if stripped == "":
                in_quote = False
            continue
        cleaned_lines.append(line)
    text = "\n".join(cleaned_lines)

    # Strip signatures
    for pattern in _RE_SIG_PATTERNS:
        text = pattern.sub("", text)

    # Strip marketing footers
    for pattern in _RE_FOOTER_PATTERNS:
        text = pattern.sub("", text)

    # Collapse excessive blank lines
    text = _RE_BLANK_LINES.sub("\n\n", text)

    return text.strip()


def truncate_for_api(
    text: str, max_chars: int = MAX_BODY_CHARS
) -> str:
    """Truncate at the last whitespace before max_chars.

    Avoids mid-word cuts for cleaner AI input.
    """
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_space = truncated.rfind(" ")
    if last_space > max_chars * 0.8:
        truncated = truncated[:last_space]
    return truncated + "\n\n[truncated]"


def preprocess_body(
    raw_text: str | None, max_chars: int = MAX_BODY_CHARS
) -> str:
    """Strip noise and truncate in one call."""
    return truncate_for_api(strip_email_noise(raw_text), max_chars)


def hash_content(text: str) -> str:
    """SHA-256 hash of content for dedup checking."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
