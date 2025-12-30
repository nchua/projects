# Strength & Recomp Coach - User Guide

## Quick Start

```bash
# Install
cd /Users/nickchua/Desktop/AI/Fitness/strength-coach
pip install -e .

# Initialize database
coach init

# Log your first workout
coach ingest examples/sample_workout.json

# See your progress
coach review
```

---

## Features Overview

### 1. Workout Tracking
- Log exercises, sets, reps, weights
- Support for variations (pause, tempo, close grip)
- Equipment tracking (barbell, dumbbell, cable)
- RPE and RIR (Reps in Reserve) tracking
- Warmup set exclusion from analytics

### 2. e1RM Estimation
- Multiple formulas: Epley (default), Brzycki, Wathan, Lombardi
- Reliable for 1-12 rep sets
- Per-set and per-exercise calculations

### 3. Personal Record Detection
- **e1RM PRs**: Best estimated 1RM
- **Rep PRs**: Best weight at 1, 3, 5, 8, 10+ reps
- Automatic detection on data import
- Improvement percentages calculated

### 4. Strength Percentiles
- Compare to general lifting population
- Adjusted for bodyweight, sex, age
- Tracked lifts: Squat, Bench, Deadlift, OHP
- Classifications: Beginner → Novice → Intermediate → Advanced → Elite

### 5. Body Weight Analysis
- 7-day and 14-day rolling averages
- Weekly change tracking
- Plateau detection (14+ days stable)
- Rapid change alerts (>2 lb/week)

### 6. Recomposition Inference
- Detects weight stable + strength increasing pattern
- Confidence levels: low, medium, high
- Includes caveats about measurement limitations

### 7. Weekly Reports
- Session summary (count, volume, RPE)
- Lift progress tables with trends
- Volume by muscle group
- Intensity distribution (rep ranges)
- Strength percentiles snapshot
- Actionable recommendations

### 8. Exercise Alias System
Recognizes common names automatically:

| You Type | System Understands |
|----------|-------------------|
| "bench", "BB bench", "flat bench" | bench_press |
| "squat", "back squat" | squat |
| "DL", "deadlift" | deadlift |
| "OHP", "press", "military press" | overhead_press |
| "pullup", "pull-ups" | pull_up |
| "curls", "bicep curl" | barbell_curl |

---

## CLI Commands Reference

### `coach init`
Initialize the database (creates `~/.strength-coach/coach.db`)

```bash
coach init
coach init --db /path/to/custom.db
```

### `coach ingest <file>`
Import workout from JSON file

```bash
coach ingest workout.json
coach ingest examples/sample_workout.json --db /custom/path.db
```

### `coach add-weight <weight>`
Log a body weight entry

```bash
coach add-weight 166.2                    # Today, in lb
coach add-weight 75.5 --unit kg           # In kg
coach add-weight 165 --date 2024-12-25    # Specific date
```

### `coach review`
Generate weekly training review

```bash
coach review                    # Current week
coach review --weeks-ago 1      # Last week
coach review -o report.md       # Save to file
```

### `coach lift <exercise>`
Show progress for specific lift

```bash
coach lift squat
coach lift "bench press"
coach lift deadlift --weeks 8   # 8-week history
```

### `coach prs`
Display all personal records

```bash
coach prs
```

### `coach weight`
Show body weight trends

```bash
coach weight              # Default 8 weeks
coach weight --weeks 12   # 12 weeks history
```

### `coach calc <weight> <reps>`
Calculate estimated 1RM

```bash
coach calc 275 5           # 275 lb x 5 reps
coach calc 100 8 --unit kg # 100 kg x 8 reps
```

### `coach export <file>`
Export all data to JSON

```bash
coach export backup.json
```

---

## How to Update Data

### Adding a New Workout

**Option 1: JSON File**

Create a file `today.json`:

```json
{
  "workout_session": {
    "date": "2024-12-30",
    "duration_minutes": 60,
    "session_rpe": 7,
    "exercises": [
      {
        "exercise_name": "Squat",
        "sets": [
          {"reps": 5, "weight": 275, "weight_unit": "lb", "rir": 2},
          {"reps": 5, "weight": 275, "weight_unit": "lb", "rir": 2},
          {"reps": 5, "weight": 275, "weight_unit": "lb", "rir": 1}
        ]
      },
      {
        "exercise_name": "Bench Press",
        "sets": [
          {"reps": 5, "weight": 185, "weight_unit": "lb"},
          {"reps": 5, "weight": 185, "weight_unit": "lb"},
          {"reps": 8, "weight": 165, "weight_unit": "lb"}
        ]
      }
    ]
  }
}
```

Then import:
```bash
coach ingest today.json
```

**Option 2: Minimal JSON**

For quick logging:

```json
{
  "date": "2024-12-30",
  "exercises": [
    {
      "exercise_name": "Squat",
      "sets": [
        {"reps": 5, "weight": 275, "weight_unit": "lb"},
        {"reps": 5, "weight": 275, "weight_unit": "lb"},
        {"reps": 5, "weight": 275, "weight_unit": "lb"}
      ]
    }
  ]
}
```

### Adding Body Weight

```bash
# Quick daily weigh-in
coach add-weight 166.2

# With date (for backfilling)
coach add-weight 165.8 --date 2024-12-28
coach add-weight 166.0 --date 2024-12-29
```

### Batch Import Weigh-ins

Create `weights.json`:

```json
{
  "bodyweight_entries": [
    {"date": "2024-12-25", "weight": 167.0, "weight_unit": "lb"},
    {"date": "2024-12-26", "weight": 166.5, "weight_unit": "lb"},
    {"date": "2024-12-27", "weight": 166.0, "weight_unit": "lb"}
  ]
}
```

Then use Python directly:

```python
import json
from strength_coach.storage import SQLiteStorage
from strength_coach.models import BodyWeightEntry, WeightUnit
from decimal import Decimal
from datetime import date

storage = SQLiteStorage()
with open("weights.json") as f:
    data = json.load(f)

for entry in data["bodyweight_entries"]:
    bw = BodyWeightEntry(
        date=date.fromisoformat(entry["date"]),
        weight=Decimal(str(entry["weight"])),
        weight_unit=WeightUnit.LB,
    )
    storage.save_bodyweight(bw)

storage.close()
```

---

## JSON Schema Reference

### Workout Session

```json
{
  "workout_session": {
    "date": "YYYY-MM-DD",           // Required
    "duration_minutes": 60,          // Optional
    "session_rpe": 7.5,              // Optional (1-10)
    "location": "home gym",          // Optional
    "notes": "Felt strong",          // Optional
    "exercises": [...]               // Required, at least 1
  }
}
```

### Exercise Performance

```json
{
  "exercise_name": "Squat",          // Required (aliases work)
  "variation": "pause",              // Optional
  "equipment": "barbell",            // Optional
  "sets": [...],                     // Required, at least 1
  "notes": "Good depth"              // Optional
}
```

### Set Record

```json
{
  "reps": 5,                         // Required (≥1)
  "weight": 275,                     // Required (≥0)
  "weight_unit": "lb",               // Optional, default "lb"
  "rir": 2,                          // Optional (0-5)
  "rpe": 8,                          // Optional (5-10)
  "is_warmup": false,                // Optional, default false
  "is_failure": false,               // Optional, default false
  "notes": "felt easy"               // Optional
}
```

### Body Weight Entry

```json
{
  "date": "YYYY-MM-DD",              // Required
  "weight": 166.2,                   // Required
  "weight_unit": "lb",               // Optional, default "lb"
  "time_of_day": "morning",          // Optional
  "bodyfat_percent": 15.0,           // Optional
  "notes": "after breakfast"         // Optional
}
```

---

## Typical Weekly Workflow

### Monday (after workout)
```bash
coach ingest monday_workout.json
coach add-weight 166.0
```

### Wednesday (after workout)
```bash
coach ingest wednesday_workout.json
coach add-weight 165.8
```

### Friday (after workout)
```bash
coach ingest friday_workout.json
coach add-weight 166.2
```

### Sunday (weekly review)
```bash
coach review
coach review -o ~/Desktop/week_review.md
```

---

## Data Location

- **Database**: `~/.strength-coach/coach.db`
- **Custom location**: Use `--db /path/to/file.db` on any command

### Backup Your Data

```bash
# Export to JSON
coach export backup_$(date +%Y%m%d).json

# Or copy database directly
cp ~/.strength-coach/coach.db ~/Backups/
```

### Reset Database

```bash
rm ~/.strength-coach/coach.db
coach init
```

---

## Tips

1. **Log consistently**: Daily weigh-ins (morning, fasted) give best trend data
2. **Include warmups**: Mark them `"is_warmup": true` so they're excluded from analytics
3. **Use RIR/RPE**: Helps track fatigue and effort over time
4. **Review weekly**: The `coach review` command surfaces insights you'd miss otherwise
5. **Track main lifts**: Squat, bench, deadlift, OHP have percentile tracking built in

---

## Future: Google Sheets Integration

The system is designed to accept JSON payloads. Future integration could:
1. Export Google Sheet to JSON via Apps Script
2. Use Apple Shortcuts to generate JSON from quick input
3. Pipe JSON directly to `coach ingest`

---

## Troubleshooting

**"No data found"**
- Check the date range: `coach lift squat --weeks 12`
- Verify JSON was imported: `coach export check.json`

**Exercise not recognized**
- System stores unrecognized names as-is
- Add aliases in `src/strength_coach/models/exercises.py`

**Import errors**
- Validate JSON syntax: `python -m json.tool workout.json`
- Check required fields: date, exercises, sets with reps/weight
