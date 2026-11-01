"""The ``book`` command line (SPEC §8.7).

Every stage command dispatches through ``bookgen.stages.run_range``, which
skips stages already done (``--force`` reruns them). Exit codes: 0 ok (flags
are not errors; ``book flags`` lists them), 1 a stage is not built yet,
2 bad inputs (``StageInputError``), 3 a model call failed or hit the cost cap.
The failed stage is recorded FAILED in the manifest either way.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import anthropic
import typer

from bookgen import bakeoff as bk
from bookgen.evals import report, run_suite
from bookgen.manifest import read_manifest, resolve_flag
from bookgen.models import Companion, StageId, Value
from bookgen.paths import SeriesPaths
from bookgen.providers.images import ImageProviderError, get_provider
from bookgen.providers.llm import (
    AnthropicProvider,
    ConfigError,
    CostCapExceeded,
    LLMOutputError,
    LLMProvider,
    LLMRefusal,
)
from bookgen.stages import StageContext, StageReport, run_range, stage_range
from bookgen.stages.base import StageInputError, not_built
from bookgen.stages.s00_intake import DEFAULT_STYLE, with_series_id

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
ForceOpt = Annotated[
    bool,
    typer.Option("--force", help="Rerun stages even if done (never the series bible)."),
]


def make_llm() -> LLMProvider:
    """The LLM provider for stage commands: one cost budget per invocation (patched in tests)."""
    return AnthropicProvider()


def _report_errors(fn: Callable[[], object]) -> None:
    """Call ``fn``; unbuilt -> one line and exit 1, bad inputs -> ``error:`` and exit 2."""
    try:
        fn()
    except NotImplementedError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    except StageInputError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except (
        CostCapExceeded,
        LLMRefusal,
        LLMOutputError,
        ConfigError,
        anthropic.APIError,
        ImageProviderError,
        bk.BudgetExceeded,
    ) as exc:
        typer.echo(f"error: {type(exc).__name__}: {exc}", err=True)
        raise typer.Exit(code=3) from exc


def _echo_reports(reports: list[StageReport]) -> None:
    """Print one line per stage: outcome, flag count, cost."""
    for r in reports:
        extra = f", {r.flags} flag(s); see `book flags`" if r.flags else ""
        cost = f" ${r.cost_usd:.4f}" if r.cost_usd else ""
        typer.echo(f"{r.stage}: {r.outcome}{extra}{cost}")


def _dispatch(ctx: StageContext, stages: list[StageId], force: bool = False) -> None:
    """Run ``stages`` through the runner and report each one."""
    _report_errors(lambda: _echo_reports(run_range(ctx, stages, llm=make_llm(), force=force)))


def _not_implemented(ref: str) -> None:
    """Report a non-stage command that is not built yet."""
    _report_errors(lambda: not_built(ref))


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

    def _init() -> None:
        full = with_series_id(ctx)
        run_range(full, [StageId.S0])
        typer.echo(f"series ready: {full.paths.root}")

    _report_errors(_init)


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
    force: ForceOpt = False,
) -> None:
    """S3 (once per series) and S4: series bible and episode plan."""
    ctx = StageContext(series_id=series, episode=episode, value=value)
    _dispatch(ctx, [StageId.S3, StageId.S4], force=force)


@app.command()
def write(series: SeriesOpt, episode: EpisodeOpt = 1, force: ForceOpt = False) -> None:
    """S5-S6: manuscript with judge loop, then illustration briefs."""
    ctx = StageContext(series_id=series, episode=episode)
    _dispatch(ctx, [StageId.S5, StageId.S6], force=force)


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
    force: ForceOpt = False,
) -> None:
    """Run stages FROM..TO inclusive (S0 takes intake inputs: use init-series)."""
    try:
        stages = stage_range(from_, to)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    ctx = StageContext(series_id=series, episode=episode, spread=spread)
    _dispatch(ctx, stages, force=force)


@app.command()
def flags(
    series: SeriesOpt,
    episode: Annotated[
        int | None, typer.Option("--episode", min=1, help="One episode; default all.")
    ] = None,
    resolve: Annotated[
        int | None,
        typer.Option("--resolve", min=0, help="Mark flag #N resolved; needs --episode."),
    ] = None,
    show_all: Annotated[bool, typer.Option("--all", help="Include resolved flags.")] = False,
) -> None:
    """List open gate flags (§3.1), or clear one with --resolve."""
    paths = SeriesPaths.for_series(series)
    if resolve is not None:
        if episode is None:
            raise typer.BadParameter("--resolve needs --episode")
        try:
            flag = resolve_flag(paths.manifest(episode), episode, resolve)
        except IndexError as exc:
            raise typer.BadParameter(str(exc)) from exc
        typer.echo(f"resolved ep{episode:02d} #{resolve} [{flag.stage}] {flag.code}")
        return
    shown = 0
    for ep in [episode] if episode else paths.episodes():
        for i, f in enumerate(read_manifest(paths.manifest(ep), ep).flags):
            if f.resolved and not show_all:
                continue
            where = f" spread {f.spread}" if f.spread else ""
            done = " (resolved)" if f.resolved else ""
            typer.echo(f"ep{ep:02d} #{i} [{f.stage}{where}] {f.code}{done}: {f.message}")
            shown += 1
    if not shown:
        typer.echo("no open flags")


@app.command()
def bakeoff(
    providers: Annotated[
        str | None, typer.Option("--providers", help="Comma-separated, e.g. gemini,flux,openai.")
    ] = None,
    sheets: Annotated[Path, typer.Option("--sheets", help="Fixture sheets directory.")] = Path(
        "examples/sheets"
    ),
    scenes: Annotated[Path, typer.Option("--scenes", help="Scene file.")] = bk.DEFAULT_SCENES,
    limit: Annotated[
        int | None, typer.Option("--limit", min=1, help="First N scenes only.")
    ] = None,
    execute: Annotated[bool, typer.Option("--execute", help="Make the image calls.")] = False,
    out: Annotated[
        Path | None, typer.Option("--out", help="Run folder (default bakeoff/<stamp>).")
    ] = None,
    judge: Annotated[
        Path | None, typer.Option("--judge", help="Score a run folder with the vision judge.")
    ] = None,
    report: Annotated[
        Path | None, typer.Option("--report", help="Write docs/bakeoff-<date>.md for a run folder.")
    ] = None,
    pin: Annotated[
        str | None, typer.Option("--pin", help="Pin this provider in --series' style.json.")
    ] = None,
    series: Annotated[str | None, typer.Option("--series", help="Series for --pin.")] = None,
) -> None:
    """Image provider bake-off (§8.3): plan (default), --execute, --judge, --report, --pin."""

    def _run() -> None:
        if pin is not None:
            if series is None:
                raise typer.BadParameter("--pin needs --series")
            style = bk.pin(SeriesPaths.for_series(series), get_provider(pin))
            typer.echo(f"pinned {style.provider}/{style.model} for series {series}")
            return
        if report is not None:
            typer.echo(f"wrote {bk.report(report)}")
            return
        config = bk.load_config(scenes)
        if judge is not None:
            judged = bk.judge(judge, config, sheets, make_llm())
            typer.echo(f"judged {len(judged)} image(s) in {judge}")
            return
        if not providers:
            raise typer.BadParameter("--providers is required to plan or execute")
        built = {name: get_provider(name) for name in providers.split(",")}
        jobs = bk.plan_jobs(built, config, limit)
        costs = bk.estimate(jobs, built, config.candidates)
        images = len(jobs) * config.candidates
        typer.echo(f"{len(jobs)} jobs, {images} images; cap ${bk.image_cap_usd():.2f}")
        for name, usd in costs.items():
            typer.echo(f"  {name} ({built[name].model}): ~${usd:.2f} at list price [VERIFY-4]")
        if not execute:
            try:
                bk.sheet_dirs(sheets, config)
            except bk.BakeoffError as exc:
                typer.echo(f"note: {exc}")
            typer.echo("dry run: add --execute to make the calls")
            return
        run_dir = out or bk.DEFAULT_OUT / bk.stamp()
        bk.execute(jobs, config, sheets, run_dir, built, log=typer.echo)
        typer.echo(f"done: {run_dir} (next: --judge {run_dir}, then --report {run_dir})")

    _report_errors(_run)


@app.command("eval")
def eval_cmd(
    suite: Annotated[
        Path, typer.Option("--suite", exists=True, file_okay=False, help="Eval suite directory.")
    ],
) -> None:
    """Run the eval set (§6.7): S3-S5 per case, scores and deltas vs the last run."""

    def _eval() -> None:
        run, previous = run_suite(suite, make_llm())
        for line in report(run, previous):
            typer.echo(line)

    _report_errors(_eval)


if __name__ == "__main__":
    app()
