"""
Server-side campaign templates and the ``data.js`` parser (control-plane
spec §7.2, ARISE v3 spec §4.3 "one seed").

``campaign_templates/owner_hybrid.json`` (beside ``app/``) is the committed
copy of the training-calendar PWA's ``PHASES`` array; the console imports it
for a target user without pasting JSON. :func:`load_phases_js` is the regex
parser the owner script used to own — it lives here so the script and the
console read the same code.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "campaign_templates"
TEMPLATE_NAMES = ("owner_hybrid",)


def _phases(value: Any, label: str) -> List[Dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label}: PHASES is not a non-empty list")
    return value


def load_template(name: str) -> List[Dict[str, Any]]:
    """The committed ``PHASES`` array for ``name`` (``KeyError`` if unknown)."""
    if name not in TEMPLATE_NAMES:
        raise KeyError(f"unknown campaign template: {name}")
    path = TEMPLATES_DIR / f"{name}.json"
    return _phases(json.loads(path.read_text(encoding="utf-8")), name)


def load_phases_js(path: Path) -> List[Dict[str, Any]]:
    """``const PHASES = [...];`` in a ``data.js`` file (JSON after the wrapper) → the list."""
    text = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.DOTALL)
    match = re.search(r"const\s+PHASES\s*=\s*", text)
    if not match:
        raise ValueError(f"{path}: no `const PHASES =` found")
    body = text[match.end():].strip().rstrip(";").rstrip()
    return _phases(json.loads(body), str(path))
