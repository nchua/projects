"""Read and write artifact models as JSON files (SPEC §3.1).

Seam: every artifact read or write goes through these two functions, so all
writes are atomic and all reads validate against the model.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


def read_model[M: BaseModel](path: Path, cls: type[M]) -> M:
    """Load and validate the JSON artifact at ``path`` as ``cls``."""
    return cls.model_validate_json(path.read_text(encoding="utf-8"))


def write_model(path: Path, model: BaseModel, exclude: set[str] | None = None) -> None:
    """Write ``model`` as indented JSON atomically (temp file, then rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(model.model_dump_json(indent=2, exclude=exclude) + "\n", encoding="utf-8")
    tmp.replace(path)
