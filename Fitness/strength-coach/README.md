# Strength & Recomp Coach

A personal fitness analytics engine that tracks workout progress, estimates 1RMs, calculates strength percentiles, and generates actionable insights.

## Features

- **Workout Tracking**: Log exercises, sets, reps, and weights with support for variations and equipment
- **e1RM Estimation**: Calculate estimated 1RM using multiple formulas (Epley, Brzycki, Wathan, etc.)
- **PR Detection**: Automatically detect personal records (e1RM and rep PRs)
- **Strength Percentiles**: Compare your lifts to population standards
- **Body Weight Trends**: 7-day rolling averages, plateau detection, and trend analysis
- **Recomposition Inference**: Detect potential body recomposition from weight + strength trends
- **Weekly Reports**: Comprehensive Markdown reports with recommendations

## Installation

```bash
# Clone the repository
cd strength-coach

# Install with pip (editable mode for development)
pip install -e .

# Or install with dev dependencies
pip install -e ".[dev]"
```

## Quick Start

### Initialize the database

```bash
coach init
```

### Log a workout

Create a JSON file with your workout data (see `examples/sample_workout.json`):

```bash
coach ingest examples/sample_workout.json
```

### Add body weight

```bash
coach add-weight 166.2 --unit lb
```

### Generate a weekly review

```bash
coach review
```

### Check progress on a specific lift

```bash
coach lift squat
```

### Calculate e1RM

```bash
coach calc 275 5  # 275 lbs for 5 reps
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `coach init` | Initialize the database |
| `coach ingest <file>` | Import a workout from JSON |
| `coach add-weight <weight>` | Log a body weight entry |
| `coach review` | Generate weekly training review |
| `coach lift <exercise>` | Show progress for a specific lift |
| `coach prs` | Display all personal records |
| `coach weight` | Show body weight trends |
| `coach calc <weight> <reps>` | Calculate e1RM |
| `coach export <file>` | Export all data to JSON |

## Workout JSON Format

```json
{
  "workout_session": {
    "date": "2024-12-29",
    "duration_minutes": 75,
    "session_rpe": 7.5,
    "exercises": [
      {
        "exercise_name": "Squat",
        "variation": "high bar",
        "equipment": "barbell",
        "sets": [
          {"reps": 5, "weight": 275, "weight_unit": "lb", "rir": 2},
          {"reps": 5, "weight": 275, "weight_unit": "lb", "rir": 2},
          {"reps": 5, "weight": 275, "weight_unit": "lb", "rir": 1}
        ]
      }
    ]
  }
}
```

## Supported Exercises

The system recognizes common exercise names and aliases:

| Exercise | Aliases |
|----------|---------|
| Squat | back squat, bb squat, barbell squat |
| Bench Press | bench, bb bench, flat bench |
| Deadlift | dl, conventional deadlift |
| Overhead Press | ohp, press, shoulder press, military press |
| Pull-up | pullup, pullups, pull-ups |
| Barbell Row | bb row, bent over row |
| ... | See `models/exercises.py` for full list |

## e1RM Formulas

The system supports multiple 1RM estimation formulas:

- **Epley** (default): `weight × (1 + reps/30)`
- **Brzycki**: `weight × 36 / (37 - reps)`
- **Lombardi**: `weight × reps^0.1`
- **Wathan**: `100 × weight / (48.8 + 53.8 × e^(-0.075 × reps))`

Estimates are considered reliable for 1-12 reps.

## Strength Percentiles

Percentiles are calculated relative to the general lifting population, adjusted for:
- Bodyweight
- Sex
- Age

Based on approximate data from Symmetric Strength standards. Tracked lifts:
- Squat
- Bench Press
- Deadlift
- Overhead Press

## Data Storage

Data is stored in SQLite by default at `~/.strength-coach/coach.db`. Use the `--db` flag to specify a custom location.

## Development

### Run tests

```bash
pytest
```

### Run tests with coverage

```bash
pytest --cov=strength_coach
```

### Type checking

```bash
mypy src/strength_coach
```

### Linting

```bash
ruff check src/strength_coach
```

## Architecture

```
src/strength_coach/
├── models/          # Pydantic data models
├── storage/         # Database layer (SQLite)
├── analytics/       # Core computations (e1RM, trends, PRs, volume)
├── percentiles/     # Strength standards
├── recomp/          # Body weight analysis
├── reporting/       # Report generation
├── agent/           # LLM integration (future)
└── cli/             # Command-line interface
```

## Future Enhancements

- Google Sheets integration for data ingestion
- Apple Shortcuts integration for quick logging
- Web dashboard
- LLM-powered coaching queries
- Training program suggestions

## License

MIT
