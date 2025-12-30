"""Google Sheets integration for workout data import."""

import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from ..models import (
    BodyWeightEntry,
    ExercisePerformance,
    SetRecord,
    WeightUnit,
    WorkoutSession,
    normalize_exercise,
)
from ..models.bodyweight import TimeOfDay


class SheetsConfig(BaseModel):
    """Configuration for Google Sheets integration."""

    credentials_path: Path
    spreadsheet_id: str
    workout_sheet_name: str = "Workouts"
    bodyweight_sheet_name: str = "Body Weight"


class SheetsSyncResult(BaseModel):
    """Result of a Google Sheets sync operation."""

    success: bool
    sessions_imported: int = 0
    bodyweight_entries_imported: int = 0
    errors: list[str] = []


# Expected column headers for workout sheet
WORKOUT_COLUMNS = [
    "Date",           # A - Required: YYYY-MM-DD
    "Exercise",       # B - Required: Exercise name
    "Set",            # C - Required: Set number (1, 2, 3...)
    "Reps",           # D - Required: Number of reps
    "Weight",         # E - Required: Weight used
    "Unit",           # F - Optional: lb or kg (default: lb)
    "RIR",            # G - Optional: Reps in Reserve
    "RPE",            # H - Optional: Rate of Perceived Exertion
    "Warmup",         # I - Optional: Y/N or TRUE/FALSE
    "Notes",          # J - Optional: Set notes
]

BODYWEIGHT_COLUMNS = [
    "Date",           # A - Required: YYYY-MM-DD
    "Weight",         # B - Required: Body weight
    "Unit",           # C - Optional: lb or kg (default: lb)
    "Time of Day",    # D - Optional: morning/afternoon/evening
    "Notes",          # E - Optional: Notes
]


SHEETS_TEMPLATE = """
# Google Sheets Template for Strength Coach

## Setup Instructions

1. Create a new Google Sheet
2. Create two sheets (tabs) named exactly:
   - "Workouts"
   - "Body Weight"

3. Set up the Workouts sheet with these columns (Row 1):
   | A    | B        | C   | D    | E      | F    | G   | H   | I      | J     |
   |------|----------|-----|------|--------|------|-----|-----|--------|-------|
   | Date | Exercise | Set | Reps | Weight | Unit | RIR | RPE | Warmup | Notes |

4. Set up the Body Weight sheet with these columns (Row 1):
   | A    | B      | C    | D           | E     |
   |------|--------|------|-------------|-------|
   | Date | Weight | Unit | Time of Day | Notes |

## Example Workout Data (starting Row 2):

| Date       | Exercise    | Set | Reps | Weight | Unit | RIR | RPE | Warmup | Notes      |
|------------|-------------|-----|------|--------|------|-----|-----|--------|------------|
| 2024-12-29 | Squat       | 1   | 5    | 135    | lb   |     |     | Y      | warmup     |
| 2024-12-29 | Squat       | 2   | 5    | 185    | lb   |     |     | Y      |            |
| 2024-12-29 | Squat       | 3   | 5    | 225    | lb   | 3   |     |        |            |
| 2024-12-29 | Squat       | 4   | 5    | 225    | lb   | 2   |     |        |            |
| 2024-12-29 | Squat       | 5   | 5    | 225    | lb   | 1   |     |        | felt heavy |
| 2024-12-29 | Bench Press | 1   | 5    | 95     | lb   |     |     | Y      |            |
| 2024-12-29 | Bench Press | 2   | 5    | 135    | lb   |     |     | Y      |            |
| 2024-12-29 | Bench Press | 3   | 5    | 165    | lb   | 2   |     |        |            |

## Example Body Weight Data:

| Date       | Weight | Unit | Time of Day | Notes  |
|------------|--------|------|-------------|--------|
| 2024-12-29 | 166.2  | lb   | morning     | fasted |
| 2024-12-28 | 165.8  | lb   | morning     |        |

## Google Service Account Setup

1. Go to Google Cloud Console (console.cloud.google.com)
2. Create a new project or select existing
3. Enable the Google Sheets API
4. Create a Service Account:
   - Go to IAM & Admin > Service Accounts
   - Create Service Account
   - Download JSON credentials
5. Share your spreadsheet with the service account email
   (found in the JSON file as "client_email")

## Usage

```bash
# View this template
coach sheets-template

# Sync from Google Sheets
coach sync-sheets --spreadsheet-id "YOUR_SPREADSHEET_ID" \\
                  --credentials ~/.config/google-creds.json

# Sync only recent data
coach sync-sheets --spreadsheet-id "YOUR_SPREADSHEET_ID" \\
                  --credentials ~/.config/google-creds.json \\
                  --since 2024-12-01
```
"""


class SheetsClient:
    """Client for reading workout data from Google Sheets."""

    def __init__(self, config: SheetsConfig):
        self.config = config
        self._service = None

    @property
    def service(self):
        """Lazily initialize the Google Sheets API service."""
        if self._service is None:
            self._service = self._build_service()
        return self._service

    def _build_service(self):
        """Build the Google Sheets API service."""
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError:
            raise ImportError(
                "Google API packages required. Install with: "
                "pip install google-auth google-api-python-client"
            )

        scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
        credentials = service_account.Credentials.from_service_account_file(
            str(self.config.credentials_path),
            scopes=scopes,
        )
        return build("sheets", "v4", credentials=credentials)

    def fetch_workouts(
        self,
        since_date: Optional[date] = None,
    ) -> tuple[list[WorkoutSession], list[str]]:
        """
        Fetch workout sessions from the spreadsheet.

        Args:
            since_date: Only return workouts on or after this date

        Returns:
            Tuple of (list of WorkoutSession, list of error messages)
        """
        sheet = self.service.spreadsheets()

        # Read workout data range (A:J for all columns)
        range_name = f"{self.config.workout_sheet_name}!A:J"
        result = sheet.values().get(
            spreadsheetId=self.config.spreadsheet_id,
            range=range_name,
        ).execute()

        rows = result.get("values", [])
        if len(rows) < 2:  # Need header + at least 1 data row
            return [], []

        # Skip header row
        return self._parse_workout_rows(rows[1:], since_date)

    def fetch_bodyweight(
        self,
        since_date: Optional[date] = None,
    ) -> tuple[list[BodyWeightEntry], list[str]]:
        """
        Fetch body weight entries from the spreadsheet.

        Args:
            since_date: Only return entries on or after this date

        Returns:
            Tuple of (list of BodyWeightEntry, list of error messages)
        """
        sheet = self.service.spreadsheets()

        range_name = f"{self.config.bodyweight_sheet_name}!A:E"
        result = sheet.values().get(
            spreadsheetId=self.config.spreadsheet_id,
            range=range_name,
        ).execute()

        rows = result.get("values", [])
        if len(rows) < 2:
            return [], []

        return self._parse_bodyweight_rows(rows[1:], since_date)

    def _parse_workout_rows(
        self,
        rows: list[list[str]],
        since_date: Optional[date],
    ) -> tuple[list[WorkoutSession], list[str]]:
        """Parse spreadsheet rows into WorkoutSession objects."""
        errors: list[str] = []
        sessions_by_date: dict[date, dict] = {}

        for row_num, row in enumerate(rows, start=2):  # Row 2 is first data row
            if not row or len(row) < 5:  # Need at least Date, Exercise, Set, Reps, Weight
                continue

            try:
                # Parse date
                date_str = row[0].strip()
                try:
                    workout_date = date.fromisoformat(date_str)
                except ValueError:
                    # Try parsing other date formats
                    for fmt in ["%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d"]:
                        try:
                            workout_date = datetime.strptime(date_str, fmt).date()
                            break
                        except ValueError:
                            continue
                    else:
                        errors.append(f"Row {row_num}: Invalid date format '{date_str}'")
                        continue

                # Skip if before since_date
                if since_date and workout_date < since_date:
                    continue

                # Parse required fields
                exercise_name = row[1].strip()
                set_num = int(row[2])
                reps = int(row[3])
                weight = Decimal(row[4].strip())

                # Parse optional fields
                unit = WeightUnit.LB
                if len(row) > 5 and row[5].strip().lower() in ("kg", "kilogram", "kilograms"):
                    unit = WeightUnit.KG

                rir = None
                if len(row) > 6 and row[6].strip():
                    rir = int(row[6])

                rpe = None
                if len(row) > 7 and row[7].strip():
                    rpe = float(row[7])

                is_warmup = False
                if len(row) > 8 and row[8].strip().lower() in ("y", "yes", "true", "1"):
                    is_warmup = True

                notes = None
                if len(row) > 9 and row[9].strip():
                    notes = row[9].strip()

                # Build set record
                set_record = SetRecord(
                    reps=reps,
                    weight=weight,
                    weight_unit=unit,
                    rir=rir,
                    rpe=rpe,
                    is_warmup=is_warmup,
                    notes=notes,
                )

                # Group by date
                if workout_date not in sessions_by_date:
                    sessions_by_date[workout_date] = {"exercises": {}}

                # Group by exercise within date
                if exercise_name not in sessions_by_date[workout_date]["exercises"]:
                    sessions_by_date[workout_date]["exercises"][exercise_name] = []

                sessions_by_date[workout_date]["exercises"][exercise_name].append(
                    (set_num, set_record)
                )

            except Exception as e:
                errors.append(f"Row {row_num}: {e}")

        # Build WorkoutSession objects
        sessions: list[WorkoutSession] = []
        for workout_date, data in sorted(sessions_by_date.items()):
            exercises: list[ExercisePerformance] = []

            for exercise_name, sets_data in data["exercises"].items():
                # Sort sets by set number and extract just the SetRecords
                sorted_sets = sorted(sets_data, key=lambda x: x[0])
                sets = [s[1] for s in sorted_sets]

                exercises.append(
                    ExercisePerformance(
                        exercise_name=exercise_name,
                        canonical_id=normalize_exercise(exercise_name),
                        sets=sets,
                    )
                )

            sessions.append(
                WorkoutSession(
                    date=workout_date,
                    exercises=exercises,
                )
            )

        return sessions, errors

    def _parse_bodyweight_rows(
        self,
        rows: list[list[str]],
        since_date: Optional[date],
    ) -> tuple[list[BodyWeightEntry], list[str]]:
        """Parse spreadsheet rows into BodyWeightEntry objects."""
        errors: list[str] = []
        entries: list[BodyWeightEntry] = []

        for row_num, row in enumerate(rows, start=2):
            if not row or len(row) < 2:  # Need at least Date, Weight
                continue

            try:
                # Parse date
                date_str = row[0].strip()
                try:
                    entry_date = date.fromisoformat(date_str)
                except ValueError:
                    for fmt in ["%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d"]:
                        try:
                            entry_date = datetime.strptime(date_str, fmt).date()
                            break
                        except ValueError:
                            continue
                    else:
                        errors.append(f"Row {row_num}: Invalid date format '{date_str}'")
                        continue

                if since_date and entry_date < since_date:
                    continue

                # Parse weight
                weight = Decimal(row[1].strip())

                # Parse optional fields
                unit = WeightUnit.LB
                if len(row) > 2 and row[2].strip().lower() in ("kg", "kilogram", "kilograms"):
                    unit = WeightUnit.KG

                time_of_day = None
                if len(row) > 3 and row[3].strip():
                    tod_str = row[3].strip().lower()
                    if tod_str in ("morning", "am"):
                        time_of_day = TimeOfDay.MORNING
                    elif tod_str in ("afternoon", "midday"):
                        time_of_day = TimeOfDay.AFTERNOON
                    elif tod_str in ("evening", "night", "pm"):
                        time_of_day = TimeOfDay.EVENING

                notes = None
                if len(row) > 4 and row[4].strip():
                    notes = row[4].strip()

                entries.append(
                    BodyWeightEntry(
                        date=entry_date,
                        weight=weight,
                        weight_unit=unit,
                        time_of_day=time_of_day,
                        notes=notes,
                    )
                )

            except Exception as e:
                errors.append(f"Row {row_num}: {e}")

        return entries, errors


def get_template() -> str:
    """Return the Google Sheets template documentation."""
    return SHEETS_TEMPLATE
