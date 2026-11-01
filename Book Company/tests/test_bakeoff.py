"""The bake-off: plan, execute (resumable, capped), judge, report, pin; fakes only."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from bookgen import bakeoff as bk
from bookgen import cli
from bookgen.models import StyleBible
from bookgen.providers.images.fake import FakeImageProvider, write_png
from bookgen.stages.base import StageContext
from tests.fakes import FakeLLM


@pytest.fixture
def sheets(tmp_path: Path) -> Path:
    """Sheets for the three fixture characters, plus one style anchor."""
    root = tmp_path / "sheets"
    for cid in ("maya", "toast", "pickles"):
        (root / cid).mkdir(parents=True)
        write_png(root / cid / "sheet.png", 8, 4, (10, 20, 30))
    (root / "anchors").mkdir()
    write_png(root / "anchors" / "a1.png", 8, 4, (40, 50, 60))
    return root


@pytest.fixture
def config() -> bk.BakeoffConfig:
    """The real scene file."""
    return bk.load_config()


def test_scene_file_matches_the_protocol(config: bk.BakeoffConfig) -> None:
    """Twenty scenes, two aspects, three candidates; two- and three-character shots present."""
    assert len(config.scenes) == 20 and config.aspects == ["2:1", "1:1"] and config.candidates == 3
    sizes = {len(s.brief.characters) for s in config.scenes}
    assert {1, 2, 3} <= sizes
    assert {c.id for s in config.scenes for c in s.brief.characters} == {"maya", "toast", "pickles"}


def test_plan_and_estimate(config: bk.BakeoffConfig) -> None:
    """Providers x scenes x aspects jobs; estimate = jobs x candidates x list price."""
    fake = {"fake": FakeImageProvider(usd_per_image=0.5)}
    jobs = bk.plan_jobs(fake, config, limit=2)
    assert [j.key for j in jobs][:2] == ["fake/s01_kite_morning_2x1", "fake/s01_kite_morning_1x1"]
    assert bk.estimate(jobs, fake, config.candidates) == {"fake": pytest.approx(4 * 3 * 0.5)}


def test_missing_sheets_is_an_input_error(config: bk.BakeoffConfig, tmp_path: Path) -> None:
    """No sheets: a clear error naming the characters (exit 2 through the CLI)."""
    with pytest.raises(bk.BakeoffError, match="maya"):
        bk.sheet_dirs(tmp_path, config)


def test_execute_resumes_records_refusals_and_writes_human_sheet(
    config: bk.BakeoffConfig, sheets: Path, tmp_path: Path
) -> None:
    """Images and refusals recorded; rerun skips done jobs; human scores survive a rerun."""
    out = tmp_path / "run"
    fake = FakeImageProvider(refuse_when="thunderstorm")
    providers = {"fake": fake}
    jobs = bk.plan_jobs(providers, config)
    first = bk.execute(jobs[:4], config, sheets, out, providers)
    assert len(first) == 4 and all(len(r.images) == 3 for r in first)
    assert all(r.images[0].path and r.images[0].path.exists() for r in first)
    assert "maya/sheet.png" in first[0].references[0] and len(first[0].prompt_hash) == 64
    sheet = out / "human_scores.csv"
    sheet.write_text(
        sheet.read_text().replace(",fake,s01_kite_morning,,", ",fake,s01_kite_morning,3,", 1)
    )

    second = bk.execute(jobs, config, sheets, out, providers)
    assert len(second) == len(jobs) - 4  # resumed
    storm = [r for r in bk.read_records(out) if r.job.scene == "s19_storm_cupboard"]
    assert storm and all(i.refused for r in storm for i in r.images)
    assert ",3," in sheet.read_text()  # the owner's score is kept


def test_execute_stops_at_the_cap(config: bk.BakeoffConfig, sheets: Path, tmp_path: Path) -> None:
    """A job whose worst case passes the cap is never sent."""
    fake = FakeImageProvider(usd_per_image=1.0)
    jobs = bk.plan_jobs({"fake": fake}, config)
    with pytest.raises(bk.BudgetExceeded):
        bk.execute(jobs, config, sheets, tmp_path / "run", {"fake": fake}, cap_usd=7.0)
    assert len(bk.read_records(tmp_path / "run")) == 2  # 2 jobs x 3 images = $6
    assert len(fake.calls) == 2


def test_judge_sends_sheets_then_candidate_and_report(
    config: bk.BakeoffConfig, sheets: Path, tmp_path: Path
) -> None:
    """The judge sees each present character's sheet, then the candidate; report sums it up."""
    out = tmp_path / "run"
    providers = {"fake": FakeImageProvider()}
    bk.execute(bk.plan_jobs(providers, config, limit=1), config, sheets, out, providers)
    score = bk.ImageScore(identity=2, style=3, brief=3, no_text=True, safe=True, notes="")
    llm = FakeLLM({"judge-s01_kite_morning": [score] * 6})
    judged = bk.judge(out, config, sheets, llm)
    assert len(judged) == 6
    call = llm.calls[0]
    assert [p.name for p in call.images] == ["sheet.png", "s01_kite_morning_2x1_c1.png"]
    assert bk.judge(out, config, sheets, llm) == []  # already judged

    path = bk.report(out, docs=tmp_path / "docs", today="2026-11-02")
    text = path.read_text()
    assert path.name == "bakeoff-2026-11-02.md"
    assert "| fake | fake-1 | 2 | 6 | 0 | 0 |" in text and "| 2.00 | 3.00 | 3.00 | 100% |" in text


def test_pin_writes_style_and_refuses_a_silent_repin(demo_series: StageContext) -> None:
    """Pin records provider/model/time once; a different provider later is refused (D5)."""
    fake = FakeImageProvider()
    style = bk.pin(demo_series.paths, fake)
    assert (style.provider, style.model) == ("fake", "fake-1") and style.pinned_at
    saved = StyleBible.model_validate_json(demo_series.paths.style.read_text())
    assert saved.provider == "fake"
    other = FakeImageProvider()
    other.name = "other"
    with pytest.raises(bk.BakeoffError, match="pinned"):
        bk.pin(demo_series.paths, other)


def test_cli_dry_run_and_execute_with_fake(sheets: Path, tmp_path: Path) -> None:
    """Dry run prints the plan and makes no calls; --execute with the fake writes a run."""
    runner = CliRunner()
    dry = runner.invoke(cli.app, ["bakeoff", "--providers", "fake", "--limit", "1"])
    assert dry.exit_code == 0, dry.output
    assert "2 jobs, 6 images" in dry.output and "dry run" in dry.output
    run_dir = tmp_path / "run"
    args = ["bakeoff", "--providers", "fake", "--limit", "1", "--sheets", str(sheets)]
    done = runner.invoke(cli.app, [*args, "--execute", "--out", str(run_dir)])
    assert done.exit_code == 0, done.output
    assert (run_dir / "results.jsonl").exists() and (run_dir / "human_scores.csv").exists()
    missing = runner.invoke(
        cli.app, ["bakeoff", "--providers", "fake", "--sheets", str(tmp_path / "none"), "--execute"]
    )
    assert missing.exit_code == 2 and "no sheet" in missing.output
