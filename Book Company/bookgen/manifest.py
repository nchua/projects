"""Read and append stage records in ``epNN/manifest.json`` (SPEC §3.1).

Seam: a stage calls ``start_stage`` before work and ``finish_stage`` after it.
"Append" means upsert by stage id: re-running a stage replaces its record,
increments ``attempts`` and accumulates ``cost_usd``. Gate failures go through
``add_flag`` (a flag, not an exception).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from bookgen.models import Flag, Manifest, StageId, StageRecord, StageStatus


def now() -> datetime:
    """Return the current UTC time (one place to patch in tests)."""
    return datetime.now(UTC)


def read_manifest(path: Path, episode: int) -> Manifest:
    """Load the manifest at ``path``, or return an empty one for ``episode``."""
    if not path.exists():
        return Manifest(episode=episode)
    return Manifest.model_validate_json(path.read_text(encoding="utf-8"))


def write_manifest(path: Path, manifest: Manifest) -> None:
    """Write ``manifest`` atomically (temp file, then rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def start_stage(path: Path, episode: int, stage: StageId) -> Manifest:
    """Record that ``stage`` has started; returns the updated manifest."""
    manifest = read_manifest(path, episode)
    prev = manifest.stages.get(stage)
    manifest.stages[stage] = StageRecord(
        status=StageStatus.STARTED,
        attempts=prev.attempts + 1 if prev else 1,
        cost_usd=prev.cost_usd if prev else 0.0,
        started=now(),
    )
    write_manifest(path, manifest)
    return manifest


def finish_stage(
    path: Path,
    episode: int,
    stage: StageId,
    status: StageStatus,
    *,
    model: str | None = None,
    provider: str | None = None,
    cost_usd: float = 0.0,
) -> Manifest:
    """Close the current run of ``stage`` with ``status`` and add its cost."""
    manifest = read_manifest(path, episode)
    rec = manifest.stages.get(stage) or StageRecord(status=StageStatus.STARTED, started=now())
    manifest.stages[stage] = rec.model_copy(
        update={
            "status": status,
            "model": model,
            "provider": provider,
            "cost_usd": rec.cost_usd + cost_usd,
            "finished": now(),
        }
    )
    write_manifest(path, manifest)
    return manifest


def add_flag(
    path: Path, episode: int, stage: StageId, code: str, message: str, spread: int | None = None
) -> Manifest:
    """Append a gate-failure flag to the manifest (§3.1)."""
    manifest = read_manifest(path, episode)
    manifest.flags.append(
        Flag(stage=stage, code=code, message=message, spread=spread, created=now())
    )
    write_manifest(path, manifest)
    return manifest
