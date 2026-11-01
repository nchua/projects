"""Read and append stage records in ``epNN/manifest.json`` (SPEC §3.1).

Seam: only the runner (``bookgen.stages.run_range``) calls ``start_stage`` and
``finish_stage``; stages return their checks instead. "Append" means upsert by
stage id: re-running a stage replaces its record, increments ``attempts`` and
accumulates ``cost_usd``. Gate failures become flags via ``add_flag``. Starting
a stage again resolves its earlier open flags (they described output that is
about to be replaced).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from bookgen.io import read_model, write_model
from bookgen.models import CheckResult, Flag, Manifest, StageId, StageRecord, StageStatus


def now() -> datetime:
    """Return the current UTC time (one place to patch in tests)."""
    return datetime.now(UTC)


def read_manifest(path: Path, episode: int) -> Manifest:
    """Load the manifest at ``path``, or return an empty one for ``episode``."""
    if not path.exists():
        return Manifest(episode=episode)
    return read_model(path, Manifest)


def write_manifest(path: Path, manifest: Manifest) -> None:
    """Write ``manifest`` atomically."""
    write_model(path, manifest)


def start_stage(path: Path, episode: int, stage: StageId) -> Manifest:
    """Record that ``stage`` has started and supersede its open flags; returns the manifest."""
    manifest = read_manifest(path, episode)
    for flag in manifest.flags:
        if flag.stage is stage and not flag.resolved:
            flag.resolved = True
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
    checks: list[CheckResult] | None = None,
) -> Manifest:
    """Close the current run of ``stage`` with ``status``, its checks, and add its cost."""
    manifest = read_manifest(path, episode)
    rec = manifest.stages.get(stage) or StageRecord(status=StageStatus.STARTED, started=now())
    manifest.stages[stage] = rec.model_copy(
        update={
            "status": status,
            "model": model,
            "provider": provider,
            "cost_usd": rec.cost_usd + cost_usd,
            "finished": now(),
            "checks": checks or [],
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


def resolve_flag(path: Path, episode: int, index: int) -> Flag:
    """Mark flag ``index`` (0-based, as ``book flags`` numbers them) resolved; returns it."""
    manifest = read_manifest(path, episode)
    if not 0 <= index < len(manifest.flags):
        raise IndexError(f"episode {episode} has no flag #{index}")
    manifest.flags[index].resolved = True
    write_manifest(path, manifest)
    return manifest.flags[index]
