"""CLI commands for strength coach."""

import json
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown

from ..models import (
    BodyWeightEntry,
    ExercisePerformance,
    SetRecord,
    WorkoutSession,
    WorkoutSessionInput,
    UserProfile,
    DEFAULT_USER_PROFILE,
    normalize_exercise,
    get_exercise,
)
from ..storage import SQLiteStorage
from ..analytics import (
    estimate_e1rm,
    get_exercise_trend,
    build_pr_history,
    format_pr_for_display,
)
from ..percentiles import default_provider
from ..reporting import generate_weekly_review, generate_weekly_report_markdown

app = typer.Typer(
    name="coach",
    help="Personal Strength & Recomp Coach - Track workouts, analyze progress, get recommendations.",
    no_args_is_help=True,
)
console = Console()

# Default database path
DEFAULT_DB_PATH = Path.home() / ".strength-coach" / "coach.db"


def get_storage(db_path: Optional[Path] = None) -> SQLiteStorage:
    """Get storage instance."""
    path = db_path or DEFAULT_DB_PATH
    return SQLiteStorage(path)


@app.command()
def ingest(
    file: Path = typer.Argument(..., help="JSON file with workout data"),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Database path"),
) -> None:
    """Ingest a workout session from a JSON file."""
    if not file.exists():
        console.print(f"[red]Error: File not found: {file}[/red]")
        raise typer.Exit(1)

    try:
        with open(file) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        console.print(f"[red]Error: Invalid JSON: {e}[/red]")
        raise typer.Exit(1)

    # Parse workout session
    try:
        if "workout_session" in data:
            session_data = data["workout_session"]
        else:
            session_data = data

        # Convert date string to date object
        if isinstance(session_data.get("date"), str):
            session_data["date"] = date.fromisoformat(session_data["date"])

        # Parse exercises
        exercises = []
        for ex_data in session_data.get("exercises", []):
            sets = [SetRecord(**s) for s in ex_data.pop("sets", [])]
            exercise = ExercisePerformance(sets=sets, **ex_data)
            exercise.canonical_id = normalize_exercise(exercise.exercise_name)
            exercises.append(exercise)

        session_data["exercises"] = exercises
        session = WorkoutSession(**session_data)

    except Exception as e:
        console.print(f"[red]Error parsing workout: {e}[/red]")
        raise typer.Exit(1)

    # Save to storage
    storage = get_storage(db_path)
    try:
        session_id = storage.save_session(session)
        console.print(f"[green]Workout saved successfully![/green]")
        console.print(f"Session ID: {session_id}")
        console.print(f"Date: {session.date}")
        console.print(f"Exercises: {len(session.exercises)}")
        console.print(f"Total sets: {session.total_sets}")
    finally:
        storage.close()


@app.command()
def add_weight(
    weight: float = typer.Argument(..., help="Body weight"),
    unit: str = typer.Option("lb", "--unit", "-u", help="Unit (lb or kg)"),
    date_str: Optional[str] = typer.Option(None, "--date", "-d", help="Date (YYYY-MM-DD)"),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Database path"),
) -> None:
    """Add a body weight entry."""
    from ..models.workout import WeightUnit

    entry_date = date.fromisoformat(date_str) if date_str else date.today()
    weight_unit = WeightUnit.KG if unit.lower() == "kg" else WeightUnit.LB

    entry = BodyWeightEntry(
        date=entry_date,
        weight=Decimal(str(weight)),
        weight_unit=weight_unit,
    )

    storage = get_storage(db_path)
    try:
        entry_id = storage.save_bodyweight(entry)
        console.print(f"[green]Weight recorded: {weight} {unit} on {entry_date}[/green]")
    finally:
        storage.close()


@app.command()
def review(
    weeks_ago: int = typer.Option(0, "--weeks-ago", "-w", help="Weeks back to review"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save to file"),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Database path"),
) -> None:
    """Generate a weekly training review."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks_ago)

    storage = get_storage(db_path)
    try:
        review_data = generate_weekly_review(storage, week_start)
        markdown = generate_weekly_report_markdown(review_data)

        if output:
            output.write_text(markdown)
            console.print(f"[green]Report saved to {output}[/green]")
        else:
            console.print(Markdown(markdown))

    finally:
        storage.close()


@app.command()
def lift(
    exercise: str = typer.Argument(..., help="Exercise name"),
    weeks: int = typer.Option(12, "--weeks", "-w", help="Weeks of history"),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Database path"),
) -> None:
    """Show progress for a specific lift."""
    canonical_id = normalize_exercise(exercise)
    exercise_info = get_exercise(canonical_id)

    storage = get_storage(db_path)
    try:
        history = storage.get_exercise_history(canonical_id)

        if not history:
            console.print(f"[yellow]No data found for {exercise}[/yellow]")
            raise typer.Exit(0)

        trend = get_exercise_trend(history, weeks=weeks)
        prs = build_pr_history(history, canonical_id)

        # Display name
        display_name = exercise_info.display_name if exercise_info else exercise

        console.print(Panel(f"[bold]{display_name}[/bold] Progress", expand=False))
        console.print()

        # Current stats
        table = Table(title="Current Status")
        table.add_column("Metric")
        table.add_column("Value")

        table.add_row("Current e1RM", f"{trend['current_e1rm']:.0f} lb")
        table.add_row("4 Weeks Ago", f"{trend['e1rm_n_weeks_ago']:.0f} lb")
        table.add_row("Change", f"{trend['e1rm_change_pct']:+.1f}%")
        table.add_row("Trend", trend["trend_direction"].title())

        console.print(table)
        console.print()

        # PRs
        if prs:
            console.print("[bold]Personal Records:[/bold]")
            for pr in prs.values():
                console.print(f"  {format_pr_for_display(pr)}")
            console.print()

        # Percentile
        latest_weight = storage.get_latest_bodyweight()
        bodyweight = (
            latest_weight.weight_lb
            if latest_weight
            else DEFAULT_USER_PROFILE.default_bodyweight_lb
        )

        if canonical_id in default_provider.supported_lifts:
            pct = default_provider.get_percentile(
                canonical_id,
                trend["current_e1rm"],
                bodyweight,
                DEFAULT_USER_PROFILE.sex,
                DEFAULT_USER_PROFILE.age,
            )
            console.print(f"[bold]Strength Level:[/bold] {pct.percentile:.0f}th percentile ({pct.classification})")
            console.print(f"Bodyweight Multiple: {pct.bodyweight_multiple:.2f}x")

    finally:
        storage.close()


@app.command()
def prs(
    db_path: Optional[Path] = typer.Option(None, "--db", help="Database path"),
) -> None:
    """Show all personal records."""
    storage = get_storage(db_path)
    try:
        all_exercises = storage.get_all_exercises()

        if not all_exercises:
            console.print("[yellow]No exercise data found.[/yellow]")
            raise typer.Exit(0)

        table = Table(title="Personal Records")
        table.add_column("Exercise")
        table.add_column("e1RM")
        table.add_column("5 Rep PR")
        table.add_column("Best Set")

        for exercise_id in all_exercises:
            history = storage.get_exercise_history(exercise_id)
            prs_dict = build_pr_history(history, exercise_id)

            exercise_info = get_exercise(exercise_id)
            display_name = exercise_info.display_name if exercise_info else exercise_id

            e1rm = prs_dict.get("e1rm")
            rep5 = prs_dict.get("rep_pr_5")

            e1rm_str = f"{e1rm.value:.0f} lb" if e1rm else "-"
            rep5_str = f"{rep5.value:.0f} lb" if rep5 else "-"

            best_set_str = "-"
            if e1rm and e1rm.weight and e1rm.reps:
                best_set_str = f"{e1rm.weight:.0f} x {e1rm.reps}"

            table.add_row(display_name, e1rm_str, rep5_str, best_set_str)

        console.print(table)

    finally:
        storage.close()


@app.command()
def weight(
    weeks: int = typer.Option(8, "--weeks", "-w", help="Weeks of history"),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Database path"),
) -> None:
    """Show body weight trends."""
    from ..recomp import analyze_weight_trends, get_weight_history_summary

    storage = get_storage(db_path)
    try:
        entries = storage.get_bodyweight_entries(
            start_date=date.today() - timedelta(weeks=weeks)
        )

        if not entries:
            console.print("[yellow]No weight data found.[/yellow]")
            raise typer.Exit(0)

        analysis = analyze_weight_trends(entries)

        console.print(Panel("[bold]Body Weight Analysis[/bold]", expand=False))
        console.print()

        table = Table()
        table.add_column("Metric")
        table.add_column("Value")

        table.add_row("Current Weight", f"{analysis.current_weight:.1f} lb")
        table.add_row("7-Day Average", f"{analysis.rolling_7day_avg:.1f} lb")
        table.add_row("Weekly Change", f"{analysis.weekly_change_lb:+.1f} lb")
        table.add_row("4-Week Trend", analysis.trend_4wk.title())

        if analysis.days_at_plateau > 0:
            table.add_row("Plateau Days", str(analysis.days_at_plateau))

        console.print(table)

        if analysis.alerts:
            console.print()
            console.print("[bold]Alerts:[/bold]")
            for alert in analysis.alerts:
                console.print(f"  [yellow]- {alert}[/yellow]")

    finally:
        storage.close()


@app.command()
def calc(
    weight: float = typer.Argument(..., help="Weight lifted"),
    reps: int = typer.Argument(..., help="Reps completed"),
    unit: str = typer.Option("lb", "--unit", "-u", help="Unit (lb or kg)"),
) -> None:
    """Calculate estimated 1RM from weight and reps."""
    from ..analytics import E1RMFormula, estimate_e1rm_multi

    weight_decimal = Decimal(str(weight))

    results = estimate_e1rm_multi(
        weight_decimal,
        reps,
        [E1RMFormula.EPLEY, E1RMFormula.BRZYCKI, E1RMFormula.WATHAN],
    )

    console.print(f"[bold]e1RM Estimates for {weight} {unit} x {reps}:[/bold]")
    console.print()

    table = Table()
    table.add_column("Formula")
    table.add_column("e1RM")

    for formula, value in results.items():
        table.add_row(formula.value.title(), f"{value:.1f} {unit}")

    console.print(table)

    if reps > 12:
        console.print()
        console.print("[yellow]Note: e1RM estimates are less reliable for reps > 12[/yellow]")


@app.command()
def init(
    db_path: Optional[Path] = typer.Option(None, "--db", help="Database path"),
) -> None:
    """Initialize the database."""
    path = db_path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    storage = SQLiteStorage(path)
    storage.close()

    console.print(f"[green]Database initialized at {path}[/green]")


@app.command()
def export(
    output: Path = typer.Argument(..., help="Output JSON file"),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Database path"),
) -> None:
    """Export all data to JSON."""
    storage = get_storage(db_path)
    try:
        sessions = storage.get_sessions()
        weights = storage.get_bodyweight_entries()
        blocks = storage.get_program_blocks()

        data = {
            "sessions": [s.model_dump(mode="json") for s in sessions],
            "bodyweight": [w.model_dump(mode="json") for w in weights],
            "program_blocks": [b.model_dump(mode="json") for b in blocks],
            "exported_at": date.today().isoformat(),
        }

        with open(output, "w") as f:
            json.dump(data, f, indent=2, default=str)

        console.print(f"[green]Data exported to {output}[/green]")
        console.print(f"Sessions: {len(sessions)}")
        console.print(f"Weight entries: {len(weights)}")
        console.print(f"Program blocks: {len(blocks)}")

    finally:
        storage.close()


@app.command("import-screenshot")
def import_screenshot(
    file: Path = typer.Argument(..., help="Screenshot image file"),
    source: str = typer.Option(
        "auto",
        "--source", "-s",
        help="Data source: whoop, apple_fitness, or auto (detect)",
    ),
    date_str: Optional[str] = typer.Option(
        None,
        "--date", "-d",
        help="Override date (YYYY-MM-DD)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show extracted data without saving",
    ),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Database path"),
) -> None:
    """Import activity data from a fitness tracker screenshot."""
    from ..models.activity import ActivitySource
    from ..ingestion.screenshot import extract_from_screenshot, detect_source

    if not file.exists():
        console.print(f"[red]Error: File not found: {file}[/red]")
        raise typer.Exit(1)

    # Parse source
    activity_source: Optional[ActivitySource] = None
    if source != "auto":
        try:
            activity_source = ActivitySource(source.lower())
        except ValueError:
            console.print(f"[red]Error: Invalid source '{source}'. Use: whoop, apple_fitness, or auto[/red]")
            raise typer.Exit(1)

    # Parse date override
    date_override = None
    if date_str:
        try:
            date_override = date.fromisoformat(date_str)
        except ValueError:
            console.print(f"[red]Error: Invalid date format. Use YYYY-MM-DD[/red]")
            raise typer.Exit(1)

    console.print(f"[bold]Processing screenshot:[/bold] {file}")

    # Auto-detect source if needed
    if activity_source is None:
        console.print("Detecting source...")
        activity_source = detect_source(file)
        console.print(f"Detected: [cyan]{activity_source.value}[/cyan]")

    # Extract data
    console.print("Extracting activity data...")
    result = extract_from_screenshot(file, activity_source, date_override)

    if not result.success:
        console.print(f"[red]Error: {result.error}[/red]")
        if result.raw_response:
            console.print("[dim]Raw response:[/dim]")
            console.print(result.raw_response[:500])
        raise typer.Exit(1)

    entry = result.entry
    if not entry:
        console.print("[red]Error: No data extracted[/red]")
        raise typer.Exit(1)

    # Display extracted data
    console.print()
    console.print(Panel(f"[bold]Activity Data - {entry.date}[/bold]", expand=False))

    table = Table()
    table.add_column("Metric")
    table.add_column("Value")

    if entry.steps:
        table.add_row("Steps", f"{entry.steps:,}")
    if entry.active_calories:
        table.add_row("Active Calories", f"{entry.active_calories:,}")
    if entry.total_calories:
        table.add_row("Total Calories", f"{entry.total_calories:,}")
    if entry.active_minutes:
        table.add_row("Active Minutes", str(entry.active_minutes))

    # Whoop metrics
    if entry.strain is not None:
        table.add_row("Strain", f"{entry.strain:.1f}")
    if entry.recovery_score is not None:
        table.add_row("Recovery", f"{entry.recovery_score}%")
    if entry.hrv is not None:
        table.add_row("HRV", f"{entry.hrv} ms")
    if entry.resting_heart_rate is not None:
        table.add_row("Resting HR", f"{entry.resting_heart_rate} bpm")
    if entry.sleep_hours is not None:
        table.add_row("Sleep", f"{entry.sleep_hours:.1f} hrs")

    # Apple rings
    if entry.move_calories is not None:
        table.add_row("Move (Red Ring)", f"{entry.move_calories:,} cal")
    if entry.exercise_minutes is not None:
        table.add_row("Exercise (Green Ring)", f"{entry.exercise_minutes} min")
    if entry.stand_hours is not None:
        table.add_row("Stand (Blue Ring)", f"{entry.stand_hours} hrs")

    console.print(table)

    # Show activities
    if entry.activities:
        console.print()
        console.print("[bold]Activities:[/bold]")
        for activity in entry.activities:
            parts = [f"  - {activity.activity_type.value.title()}"]
            if activity.duration_minutes:
                parts.append(f"{activity.duration_minutes} min")
            if activity.calories_burned:
                parts.append(f"{activity.calories_burned} cal")
            console.print(" | ".join(parts))

    if dry_run:
        console.print()
        console.print("[yellow]Dry run - data not saved[/yellow]")
    else:
        storage = get_storage(db_path)
        try:
            entry_id = storage.save_activity(entry)
            console.print()
            console.print(f"[green]Activity saved successfully![/green]")
            console.print(f"Entry ID: {entry_id}")
        finally:
            storage.close()


@app.command("sync-sheets")
def sync_sheets(
    spreadsheet_id: str = typer.Option(
        ...,
        "--spreadsheet-id",
        help="Google Sheets spreadsheet ID",
    ),
    credentials: Path = typer.Option(
        ...,
        "--credentials",
        help="Path to service account credentials JSON",
    ),
    since: Optional[str] = typer.Option(
        None,
        "--since",
        help="Only sync data since date (YYYY-MM-DD)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be imported without saving",
    ),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Database path"),
) -> None:
    """Sync workout data from Google Sheets."""
    from ..ingestion.sheets import SheetsClient, SheetsConfig

    if not credentials.exists():
        console.print(f"[red]Error: Credentials file not found: {credentials}[/red]")
        raise typer.Exit(1)

    # Parse since date
    since_date = None
    if since:
        try:
            since_date = date.fromisoformat(since)
        except ValueError:
            console.print(f"[red]Error: Invalid date format. Use YYYY-MM-DD[/red]")
            raise typer.Exit(1)

    config = SheetsConfig(
        credentials_path=credentials,
        spreadsheet_id=spreadsheet_id,
    )

    console.print(f"[bold]Connecting to Google Sheets...[/bold]")

    try:
        client = SheetsClient(config)
    except ImportError as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print("Install with: pip install 'strength-coach[sheets]'")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error connecting to Google Sheets: {e}[/red]")
        raise typer.Exit(1)

    # Fetch workouts
    console.print("Fetching workouts...")
    try:
        sessions, workout_errors = client.fetch_workouts(since_date)
    except Exception as e:
        console.print(f"[red]Error fetching workouts: {e}[/red]")
        raise typer.Exit(1)

    # Fetch body weight
    console.print("Fetching body weight entries...")
    try:
        weight_entries, weight_errors = client.fetch_bodyweight(since_date)
    except Exception as e:
        console.print(f"[red]Error fetching body weight: {e}[/red]")
        raise typer.Exit(1)

    # Display results
    console.print()
    console.print(Panel("[bold]Sync Summary[/bold]", expand=False))

    console.print(f"Workout sessions found: [cyan]{len(sessions)}[/cyan]")
    console.print(f"Body weight entries found: [cyan]{len(weight_entries)}[/cyan]")

    if workout_errors or weight_errors:
        console.print()
        console.print("[yellow]Warnings:[/yellow]")
        for err in workout_errors[:5]:
            console.print(f"  [dim]- {err}[/dim]")
        for err in weight_errors[:5]:
            console.print(f"  [dim]- {err}[/dim]")
        if len(workout_errors) + len(weight_errors) > 10:
            console.print(f"  [dim]... and {len(workout_errors) + len(weight_errors) - 10} more[/dim]")

    if sessions:
        console.print()
        console.print("[bold]Workouts:[/bold]")
        for session in sessions[:5]:
            exercises_str = ", ".join(session.exercise_names[:3])
            if len(session.exercises) > 3:
                exercises_str += f" +{len(session.exercises) - 3} more"
            console.print(f"  {session.date}: {exercises_str}")
        if len(sessions) > 5:
            console.print(f"  ... and {len(sessions) - 5} more sessions")

    if dry_run:
        console.print()
        console.print("[yellow]Dry run - data not saved[/yellow]")
    else:
        storage = get_storage(db_path)
        try:
            sessions_saved = 0
            weights_saved = 0

            for session in sessions:
                storage.save_session(session)
                sessions_saved += 1

            for entry in weight_entries:
                storage.save_bodyweight(entry)
                weights_saved += 1

            console.print()
            console.print(f"[green]Sync complete![/green]")
            console.print(f"Sessions saved: {sessions_saved}")
            console.print(f"Weight entries saved: {weights_saved}")

        finally:
            storage.close()


@app.command("sheets-template")
def sheets_template(
    output: Optional[Path] = typer.Option(
        None,
        "--output", "-o",
        help="Save template instructions to file",
    ),
) -> None:
    """Show Google Sheets template structure for workout logging."""
    from ..ingestion.sheets import get_template

    template = get_template()

    if output:
        output.write_text(template)
        console.print(f"[green]Template saved to {output}[/green]")
    else:
        console.print(Markdown(template))


@app.command("process-folder")
def process_folder(
    folder: Path = typer.Argument(..., help="Folder containing screenshot images"),
    source: str = typer.Option(
        "auto",
        "--source", "-s",
        help="Data source: whoop, apple_fitness, or auto (detect)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be processed without saving or moving files",
    ),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Database path"),
) -> None:
    """Process all screenshots in a folder and move processed files to archive."""
    import shutil
    from ..models.activity import ActivitySource
    from ..ingestion.screenshot import extract_from_screenshot, detect_source

    if not folder.exists():
        console.print(f"[red]Error: Folder not found: {folder}[/red]")
        raise typer.Exit(1)

    if not folder.is_dir():
        console.print(f"[red]Error: Not a directory: {folder}[/red]")
        raise typer.Exit(1)

    # Parse source
    activity_source: Optional[ActivitySource] = None
    if source != "auto":
        try:
            activity_source = ActivitySource(source.lower())
        except ValueError:
            console.print(f"[red]Error: Invalid source '{source}'. Use: whoop, apple_fitness, or auto[/red]")
            raise typer.Exit(1)

    # Find image files (excluding processed subfolder)
    image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    processed_folder = folder / "processed"

    image_files = [
        f for f in folder.iterdir()
        if f.is_file()
        and f.suffix.lower() in image_extensions
        and f.parent != processed_folder
    ]

    if not image_files:
        console.print(f"[yellow]No image files found in {folder}[/yellow]")
        raise typer.Exit(0)

    console.print(f"[bold]Found {len(image_files)} image(s) to process[/bold]")
    console.print()

    # Create processed folder if needed
    if not dry_run:
        processed_folder.mkdir(exist_ok=True)

    # Process each file
    success_count = 0
    fail_count = 0
    storage = None if dry_run else get_storage(db_path)

    try:
        for image_file in image_files:
            console.print(f"Processing: [cyan]{image_file.name}[/cyan]")

            # Detect source if auto
            file_source = activity_source
            if file_source is None:
                try:
                    file_source = detect_source(image_file)
                    console.print(f"  Detected: {file_source.value}")
                except Exception as e:
                    console.print(f"  [red]Failed to detect source: {e}[/red]")
                    fail_count += 1
                    continue

            # Extract data
            try:
                result = extract_from_screenshot(image_file, file_source)
            except Exception as e:
                console.print(f"  [red]Extraction failed: {e}[/red]")
                fail_count += 1
                continue

            if not result.success or not result.entry:
                console.print(f"  [red]Extraction failed: {result.error}[/red]")
                fail_count += 1
                continue

            entry = result.entry
            console.print(f"  Date: {entry.date}")

            # Show some extracted data
            metrics = []
            if entry.steps:
                metrics.append(f"steps={entry.steps:,}")
            if entry.active_calories:
                metrics.append(f"cal={entry.active_calories}")
            if entry.strain is not None:
                metrics.append(f"strain={entry.strain:.1f}")
            if entry.recovery_score is not None:
                metrics.append(f"recovery={entry.recovery_score}%")
            if entry.move_calories is not None:
                metrics.append(f"move={entry.move_calories}")
            if entry.exercise_minutes is not None:
                metrics.append(f"exercise={entry.exercise_minutes}min")

            if metrics:
                console.print(f"  Data: {', '.join(metrics)}")

            if dry_run:
                console.print(f"  [yellow]Dry run - would save and move to processed/[/yellow]")
                success_count += 1
            else:
                # Save to database
                try:
                    storage.save_activity(entry)
                except Exception as e:
                    console.print(f"  [red]Failed to save: {e}[/red]")
                    fail_count += 1
                    continue

                # Move to processed folder
                dest = processed_folder / image_file.name
                # Handle duplicate filenames
                if dest.exists():
                    stem = image_file.stem
                    suffix = image_file.suffix
                    counter = 1
                    while dest.exists():
                        dest = processed_folder / f"{stem}_{counter}{suffix}"
                        counter += 1

                shutil.move(str(image_file), str(dest))
                console.print(f"  [green]Saved and moved to processed/[/green]")
                success_count += 1

            console.print()

    finally:
        if storage:
            storage.close()

    # Summary
    console.print(f"[bold]Summary:[/bold] {success_count} succeeded, {fail_count} failed")


@app.command("setup-watcher")
def setup_watcher(
    folder: Path = typer.Argument(..., help="Folder to watch for screenshots"),
    source: str = typer.Option(
        "auto",
        "--source", "-s",
        help="Data source: whoop, apple_fitness, or auto (skip detection to save API calls)",
    ),
    uninstall: bool = typer.Option(
        False,
        "--uninstall",
        help="Remove the watcher instead of installing",
    ),
) -> None:
    """Set up a macOS launchd watcher to auto-process screenshots."""
    import subprocess

    plist_name = "com.strength-coach.screenshot-watcher.plist"
    plist_path = Path.home() / "Library" / "LaunchAgents" / plist_name

    if uninstall:
        if plist_path.exists():
            # Unload first
            subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
            plist_path.unlink()
            console.print(f"[green]Watcher uninstalled[/green]")
        else:
            console.print(f"[yellow]Watcher not installed[/yellow]")
        return

    # Validate source
    if source != "auto":
        from ..models.activity import ActivitySource
        try:
            ActivitySource(source.lower())
        except ValueError:
            console.print(f"[red]Error: Invalid source '{source}'. Use: whoop, apple_fitness, or auto[/red]")
            raise typer.Exit(1)

    # Find the coach executable
    coach_path = subprocess.run(
        ["which", "coach"],
        capture_output=True,
        text=True,
    ).stdout.strip()

    if not coach_path:
        console.print("[red]Error: 'coach' command not found in PATH[/red]")
        raise typer.Exit(1)

    # Resolve folder to absolute path
    folder = folder.resolve()

    # Create the folder if it doesn't exist
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "processed").mkdir(exist_ok=True)

    # Build program arguments with optional source
    program_args = [
        f"<string>{coach_path}</string>",
        "<string>process-folder</string>",
        f"<string>{folder}</string>",
    ]
    if source != "auto":
        program_args.extend([
            "<string>--source</string>",
            f"<string>{source}</string>",
        ])

    program_args_xml = "\n        ".join(program_args)

    # Create plist content
    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.strength-coach.screenshot-watcher</string>
    <key>ProgramArguments</key>
    <array>
        {program_args_xml}
    </array>
    <key>WatchPaths</key>
    <array>
        <string>{folder}</string>
    </array>
    <key>RunAtLoad</key>
    <false/>
    <key>StandardOutPath</key>
    <string>{Path.home()}/.strength-coach/watcher.log</string>
    <key>StandardErrorPath</key>
    <string>{Path.home()}/.strength-coach/watcher.log</string>
</dict>
</plist>
"""

    # Ensure LaunchAgents directory exists
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    # Ensure log directory exists
    (Path.home() / ".strength-coach").mkdir(parents=True, exist_ok=True)

    # Unload existing if present
    if plist_path.exists():
        subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)

    # Write plist
    plist_path.write_text(plist_content)

    # Load the agent
    result = subprocess.run(
        ["launchctl", "load", str(plist_path)],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        console.print(f"[red]Failed to load watcher: {result.stderr}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]Screenshot watcher installed![/green]")
    console.print()
    console.print(f"Watching: [cyan]{folder}[/cyan]")
    if source != "auto":
        console.print(f"Source: [cyan]{source}[/cyan] (auto-detection disabled, saves 50% API calls)")
    else:
        console.print(f"Source: [yellow]auto-detect[/yellow] (uses 2 API calls per image)")
    console.print(f"Plist: [dim]{plist_path}[/dim]")
    console.print(f"Log: [dim]{Path.home()}/.strength-coach/watcher.log[/dim]")
    console.print()
    console.print("Drop screenshots into the folder and they'll be auto-processed.")
    console.print()
    console.print("[dim]To uninstall: coach setup-watcher --uninstall[/dim]")
    console.print("[dim]To check status: launchctl list | grep strength-coach[/dim]")


if __name__ == "__main__":
    app()
