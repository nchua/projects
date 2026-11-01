"""Versioned prompt files in ``craft/prompts/`` (SPEC §3.1: never inline strings).

A prompt file is Markdown with a small front matter and two parts::

    ---
    name: plan
    version: 1
    ---
    Role instructions (sent as the last system block, after the cached context).
    === user ===
    The per-call template, with $placeholders filled by the stage.

``version`` is bumped by hand on a meaningful change; ``sha`` is the content
hash, so a log line names exactly which text produced an output (§6.7).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import cache
from string import Template

import yaml

from bookgen.craft import CRAFT_DIR

USER_MARKER = "=== user ==="
"""Separates the role instructions from the user template."""


@dataclass(frozen=True)
class Prompt:
    """One loaded prompt file."""

    name: str
    """File stem, e.g. ``plan``."""

    version: int
    """Hand-bumped version from the front matter."""

    system: str
    """Role instructions; the last system block."""

    user_template: str
    """Per-call template with ``$placeholders``."""

    sha: str
    """First 12 hex chars of the file's SHA-256."""

    def render(self, **values: str) -> str:
        """Fill the user template; a missing placeholder raises ``KeyError``."""
        return Template(self.user_template).substitute(values)


@cache
def load_prompt(name: str) -> Prompt:
    """Load ``craft/prompts/<name>.md``."""
    raw = (CRAFT_DIR / "prompts" / f"{name}.md").read_text(encoding="utf-8")
    _, front, body = raw.split("---\n", 2)
    meta = yaml.safe_load(front)
    if meta.get("name") != name:
        raise ValueError(f"prompt {name}.md declares name {meta.get('name')!r}")
    system, sep, user = body.partition(USER_MARKER)
    if not sep:
        raise ValueError(f"prompt {name}.md has no '{USER_MARKER}' section")
    return Prompt(
        name=name,
        version=int(meta["version"]),
        system=system.strip(),
        user_template=user.strip(),
        sha=hashlib.sha256(raw.encode()).hexdigest()[:12],
    )
