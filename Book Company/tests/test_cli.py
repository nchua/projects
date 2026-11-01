"""The CLI registers every §8.7 command; init-series runs S0; the rest say so."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from bookgen.cli import app

SPEC_COMMANDS = [
    "init-series",
    "sheet",
    "plan",
    "write",
    "illustrate",
    "layout",
    "review",
    "approve",
    "run",
    "flags",
    "bakeoff",
    "eval",
]

runner = CliRunner()


def test_help_lists_every_spec_command() -> None:
    """``book --help`` lists all twelve §8.7 commands."""
    result = runner.invoke(app, ["--help"], terminal_width=200)
    assert result.exit_code == 0
    for cmd in SPEC_COMMANDS:
        assert f" {cmd} " in result.output, cmd


def test_init_series(tmp_path: Path, demo_family_path: Path) -> None:
    """The §8.7 example invocation creates the series."""
    args = ["init-series", "--family", str(demo_family_path), "--style", "gouache-warm"]
    result = runner.invoke(
        app, [*args, "--companion", "dragon"], env={"BOOKGEN_SERIES_DIR": str(tmp_path)}
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "demo" / "ep01" / "manifest.json").exists()


@pytest.mark.parametrize(
    ("args", "stage"),
    [
        (["sheet", "--series", "demo", "--character", "maya"], "S1"),
        (["illustrate", "--series", "demo", "--episode", "1", "--spread", "7"], "S7"),
        (["layout", "--series", "demo", "--episode", "1"], "S10"),
        (["review", "--series", "demo", "--episode", "1"], "S12"),
        (["approve", "--series", "demo", "--episode", "1"], "S12"),
        (["run", "--series", "demo", "--episode", "1", "--from", "S7", "--to", "S11"], "S7"),
    ],
)
def test_unbuilt_stages_say_not_implemented(tmp_path: Path, args: list[str], stage: str) -> None:
    """Stage commands print the not-implemented line naming the first unbuilt stage."""
    result = runner.invoke(app, args, env={"BOOKGEN_SERIES_DIR": str(tmp_path)})
    assert result.exit_code == 1
    assert f"not implemented (SPEC §3.3 {stage})" in result.output


def test_run_rejects_backwards_range() -> None:
    """``--from`` after ``--to`` is a usage error."""
    result = runner.invoke(app, ["run", "--series", "demo", "--from", "S9", "--to", "S5"])
    assert result.exit_code == 2


def test_run_from_s0_needs_intake(tmp_path: Path) -> None:
    """``run --from S0`` goes through the contract and fails S0's input gate (exit 2)."""
    args = ["run", "--series", "demo", "--from", "S0", "--to", "S0"]
    result = runner.invoke(app, args, env={"BOOKGEN_SERIES_DIR": str(tmp_path)})
    assert result.exit_code == 2
    assert "--family" in result.output


def test_flags_lists_and_resolves(tmp_path: Path) -> None:
    """``book flags`` lists open flags across episodes; ``--resolve`` clears one."""
    from bookgen.manifest import add_flag
    from bookgen.models import StageId
    from bookgen.paths import SeriesPaths

    env = {"BOOKGEN_SERIES_DIR": str(tmp_path)}
    paths = SeriesPaths.for_series("demo", tmp_path)
    assert "no open flags" in runner.invoke(app, ["flags", "--series", "demo"], env=env).output
    add_flag(paths.manifest(1), 1, StageId.S3, "bible_human_read", "Read the bible.")
    add_flag(paths.manifest(2), 2, StageId.S5, "word_count_high", "812 > 750", spread=None)
    out = runner.invoke(app, ["flags", "--series", "demo"], env=env).output
    assert "ep01 #0 [S3] bible_human_read" in out and "ep02 #0 [S5] word_count_high" in out

    res = runner.invoke(
        app, ["flags", "--series", "demo", "--episode", "1", "--resolve", "0"], env=env
    )
    assert res.exit_code == 0, res.output
    out = runner.invoke(app, ["flags", "--series", "demo"], env=env).output
    assert "bible_human_read" not in out and "word_count_high" in out
    bad = runner.invoke(app, ["flags", "--series", "demo", "--resolve", "0"], env=env)
    assert bad.exit_code == 2
