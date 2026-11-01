"""The ``book`` command line (SPEC §8.7).

Every command dispatches to stages through ``bookgen.stages.run_range``; a
stage that is not built yet prints ``not implemented (SPEC §3.3 S#)`` and exits 1.
Only ``init-series`` (S0) works in Phase 0 session 1.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from bookgen.models import Companion, StageId, Value
from bookgen.stages import StageContext, run_range, stage_range
from bookgen.stages.base import not_built
from bookgen.stages.s00_intake import DEFAULT_STYLE, IntakeError
from bookgen.stages.s00_intake import run as run_intake

app = typer.Typer(
    name="book",
    help="Book generation pipeline for serialized children's picture books (SPEC.md).",
    no_args_is_help=True,
    add_completion=False,
)

SeriesOpt = Annotated[str, typer.Option("--series", help="Series id, e.g. 'demo'.")]
EpisodeOpt = Annotated[int, typer.Option("--episode", min=1, help="Episode number.")]
SpreadOpt = Annotated[
    int | None, typer.Option("--spread", min=1, max=12, help="Only this spread (S7-S9).")
]


def _report_unbuilt(fn: Callable[[], object]) -> None:
    """Call ``fn``; turn a NotImplementedError into its one-line message and exit 1."""
    try:
        fn()
    except NotImplementedError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc


def _dispatch(ctx: StageContext, stages: list[StageId]) -> None:
    """Run ``stages``; report the first unbuilt stage instead of a traceback."""
    _report_unbuilt(lambda: run_range(ctx, stages))


def _not_implemented(ref: str) -> None:
    """Report a non-stage command that is not built yet."""
    _report_unbuilt(lambda: not_built(ref))


@app.command("init-series")
def init_series(
    family: Annotated[Path, typer.Option("--family", exists=True, dir_okay=False)],
    style: Annotated[str, typer.Option("--style", help="Style bible id.")] = DEFAULT_STYLE,
    companion: Annotated[
        Companion | None, typer.Option("--companion", help="Override the profile's companion.")
    ] = None,
    series: Annotated[
        str | None, typer.Option("--series", help="Series id; defaults to the family id.")
    ] = None,
) -> None:
    """S0: validate the family and create the series layout and manifest."""
    ctx = StageContext(series_id=series, family_path=family, style_id=style, companion=companion)
    try:
        paths = run_intake(ctx)
    except IntakeError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"series ready: {paths.root}")


@app.command()
def sheet(
    series: SeriesOpt,
    character: Annotated[str, typer.Option("--character", help="Person or companion id.")],
) -> None:
    """S1-S2: appearance card and character sheet for one character."""
    _dispatch(StageContext(series_id=series, character=character), [StageId.S1, StageId.S2])


@app.command()
def plan(
    series: SeriesOpt,
    episode: EpisodeOpt = 1,
    value: Annotated[Value | None, typer.Option("--value", help="Value for this episode.")] = None,
) -> None:
    """S3 on the first run, then S4: series bible and episode plan."""
    ctx = StageContext(series_id=series, episode=episode, value=value)
    first = not ctx.paths.bible.exists()
    _dispatch(ctx, [StageId.S3, StageId.S4] if first else [StageId.S4])


@app.command()
def write(series: SeriesOpt, episode: EpisodeOpt = 1) -> None:
    """S5-S6: manuscript with judge loop, then illustration briefs."""
    _dispatch(StageContext(series_id=series, episode=episode), [StageId.S5, StageId.S6])


@app.command()
def illustrate(series: SeriesOpt, episode: EpisodeOpt = 1, spread: SpreadOpt = None) -> None:
    """S7-S9: generate, QA and upscale images."""
    ctx = StageContext(series_id=series, episode=episode, spread=spread)
    _dispatch(ctx, stage_range(StageId.S7, StageId.S9))


@app.command()
def layout(series: SeriesOpt, episode: EpisodeOpt = 1) -> None:
    """S10-S11: typeset the PDFs and preflight them."""
    _dispatch(StageContext(series_id=series, episode=episode), [StageId.S10, StageId.S11])


@app.command()
def review(series: SeriesOpt, episode: EpisodeOpt = 1) -> None:
    """S12: open the preview and record rubric scores."""
    _dispatch(StageContext(series_id=series, episode=episode), [StageId.S12])


@app.command()
def approve(series: SeriesOpt, episode: EpisodeOpt = 1) -> None:
    """S12-S13: approve the book and update the ledger."""
    _dispatch(StageContext(series_id=series, episode=episode), [StageId.S12, StageId.S13])


@app.command("run")
def run_cmd(
    series: SeriesOpt,
    from_: Annotated[StageId, typer.Option("--from", help="First stage.")],
    to: Annotated[StageId, typer.Option("--to", help="Last stage.")],
    episode: EpisodeOpt = 1,
    spread: SpreadOpt = None,
) -> None:
    """Run stages FROM..TO inclusive (S0 needs init-series instead)."""
    if from_ is StageId.S0:
        typer.echo("error: S0 takes intake inputs; use `book init-series`", err=True)
        raise typer.Exit(code=2)
    try:
        stages = stage_range(from_, to)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    _dispatch(StageContext(series_id=series, episode=episode, spread=spread), stages)


@app.command()
def flags(series: SeriesOpt, episode: EpisodeOpt = 1) -> None:
    """List open gate flags for an episode."""
    _not_implemented("§3.1 flags")


@app.command()
def bakeoff(
    providers: Annotated[str, typer.Option("--providers", help="Comma-separated providers.")],
    sheets: Annotated[Path, typer.Option("--sheets", help="Fixture sheets directory.")],
) -> None:
    """Image provider bake-off."""
    _not_implemented("§8.3 bake-off")


@app.command("eval")
def eval_cmd(
    suite: Annotated[Path, typer.Option("--suite", help="Eval suite directory.")],
) -> None:
    """Run the eval set."""
    _not_implemented("§6.7 eval set")


if __name__ == "__main__":
    app()
