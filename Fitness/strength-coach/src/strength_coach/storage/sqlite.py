"""SQLite storage implementation."""

import json
import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional

from ..models import (
    ActivitySource,
    BodyWeightEntry,
    CardioActivity,
    CardioWorkoutType,
    DailyActivityEntry,
    ExercisePerformance,
    ProgramBlock,
    SetRecord,
    WeightUnit,
    WorkoutSession,
    normalize_exercise,
)
from .base import StorageBackend


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal types."""

    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


def decimal_hook(dct: dict) -> dict:
    """JSON decoder hook to restore Decimals."""
    for key in ("weight",):
        if key in dct and isinstance(dct[key], str):
            try:
                dct[key] = Decimal(dct[key])
            except Exception:
                pass
    return dct


class SQLiteStorage(StorageBackend):
    """SQLite-based storage backend."""

    def __init__(self, db_path: str | Path = "data/coach.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        """Create database tables if they don't exist."""
        cursor = self.conn.cursor()

        # Workout sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workout_sessions (
                id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                start_time TEXT,
                duration_minutes INTEGER,
                session_rpe REAL,
                notes TEXT,
                program_block_id TEXT,
                location TEXT,
                exercises_json TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Denormalized sets for efficient querying
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exercise_sets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                session_date TEXT NOT NULL,
                exercise_name TEXT NOT NULL,
                canonical_id TEXT NOT NULL,
                variation TEXT,
                equipment TEXT,
                set_number INTEGER NOT NULL,
                reps INTEGER NOT NULL,
                weight REAL NOT NULL,
                weight_unit TEXT NOT NULL,
                weight_lb REAL NOT NULL,
                rir INTEGER,
                rpe REAL,
                is_warmup INTEGER NOT NULL DEFAULT 0,
                is_failure INTEGER NOT NULL DEFAULT 0,
                notes TEXT,
                FOREIGN KEY (session_id) REFERENCES workout_sessions(id)
            )
        """)

        # Body weight entries table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bodyweight_entries (
                id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                weight REAL NOT NULL,
                weight_unit TEXT NOT NULL,
                weight_lb REAL NOT NULL,
                time_of_day TEXT,
                bodyfat_percent REAL,
                measurement_method TEXT,
                notes TEXT,
                is_post_meal INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Program blocks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS program_blocks (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT,
                primary_goal TEXT NOT NULL,
                secondary_goal TEXT,
                weekly_frequency INTEGER,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Daily activity entries table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_activity (
                id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                source TEXT NOT NULL,
                steps INTEGER,
                total_calories INTEGER,
                active_calories INTEGER,
                active_minutes INTEGER,
                strain REAL,
                recovery_score INTEGER,
                hrv INTEGER,
                resting_heart_rate INTEGER,
                sleep_hours REAL,
                sleep_quality INTEGER,
                exercise_minutes INTEGER,
                stand_hours INTEGER,
                move_calories INTEGER,
                activities_json TEXT,
                notes TEXT,
                raw_ocr_text TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, source)
            )
        """)

        # Create indexes for common queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_date
            ON workout_sessions(date)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sets_canonical_id
            ON exercise_sets(canonical_id, session_date)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_bodyweight_date
            ON bodyweight_entries(date)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_activity_date
            ON daily_activity(date)
        """)

        self.conn.commit()

    def save_session(self, session: WorkoutSession) -> str:
        """Save a workout session."""
        cursor = self.conn.cursor()

        # Normalize exercise IDs
        for ex in session.exercises:
            ex.canonical_id = normalize_exercise(ex.exercise_name)

        # Serialize exercises to JSON for full fidelity
        exercises_json = json.dumps(
            [ex.model_dump() for ex in session.exercises],
            cls=DecimalEncoder,
        )

        cursor.execute(
            """
            INSERT OR REPLACE INTO workout_sessions
            (id, date, start_time, duration_minutes, session_rpe, notes,
             program_block_id, location, exercises_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                session.id,
                session.date.isoformat(),
                session.start_time.isoformat() if session.start_time else None,
                session.duration_minutes,
                session.session_rpe,
                session.notes,
                session.program_block_id,
                session.location,
                exercises_json,
            ),
        )

        # Delete existing sets for this session (for updates)
        cursor.execute("DELETE FROM exercise_sets WHERE session_id = ?", (session.id,))

        # Insert denormalized sets
        for ex in session.exercises:
            for set_num, set_record in enumerate(ex.sets, 1):
                cursor.execute(
                    """
                    INSERT INTO exercise_sets
                    (session_id, session_date, exercise_name, canonical_id, variation,
                     equipment, set_number, reps, weight, weight_unit, weight_lb,
                     rir, rpe, is_warmup, is_failure, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        session.id,
                        session.date.isoformat(),
                        ex.exercise_name,
                        ex.canonical_id,
                        ex.variation,
                        ex.equipment,
                        set_num,
                        set_record.reps,
                        float(set_record.weight),
                        set_record.weight_unit.value,
                        float(set_record.weight_lb),
                        set_record.rir,
                        set_record.rpe,
                        1 if set_record.is_warmup else 0,
                        1 if set_record.is_failure else 0,
                        set_record.notes,
                    ),
                )

        self.conn.commit()
        return session.id

    def get_session(self, session_id: str) -> Optional[WorkoutSession]:
        """Retrieve a session by ID."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM workout_sessions WHERE id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_session(row)

    def get_sessions(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: Optional[int] = None,
    ) -> list[WorkoutSession]:
        """Retrieve sessions within a date range."""
        cursor = self.conn.cursor()
        query = "SELECT * FROM workout_sessions WHERE 1=1"
        params: list = []

        if start_date:
            query += " AND date >= ?"
            params.append(start_date.isoformat())
        if end_date:
            query += " AND date <= ?"
            params.append(end_date.isoformat())

        query += " ORDER BY date DESC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        cursor.execute(query, params)
        return [self._row_to_session(row) for row in cursor.fetchall()]

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM exercise_sets WHERE session_id = ?", (session_id,))
        cursor.execute("DELETE FROM workout_sessions WHERE id = ?", (session_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def save_bodyweight(self, entry: BodyWeightEntry) -> str:
        """Save a body weight entry."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO bodyweight_entries
            (id, date, weight, weight_unit, weight_lb, time_of_day,
             bodyfat_percent, measurement_method, notes, is_post_meal)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                entry.id,
                entry.date.isoformat(),
                float(entry.weight),
                entry.weight_unit.value,
                float(entry.weight_lb),
                entry.time_of_day.value if entry.time_of_day else None,
                entry.bodyfat_percent,
                entry.measurement_method.value if entry.measurement_method else None,
                entry.notes,
                1 if entry.is_post_meal else 0,
            ),
        )
        self.conn.commit()
        return entry.id

    def get_bodyweight(self, entry_id: str) -> Optional[BodyWeightEntry]:
        """Retrieve a body weight entry by ID."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM bodyweight_entries WHERE id = ?",
            (entry_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_bodyweight(row)

    def get_bodyweight_entries(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: Optional[int] = None,
    ) -> list[BodyWeightEntry]:
        """Retrieve body weight entries within a date range."""
        cursor = self.conn.cursor()
        query = "SELECT * FROM bodyweight_entries WHERE 1=1"
        params: list = []

        if start_date:
            query += " AND date >= ?"
            params.append(start_date.isoformat())
        if end_date:
            query += " AND date <= ?"
            params.append(end_date.isoformat())

        query += " ORDER BY date DESC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        cursor.execute(query, params)
        return [self._row_to_bodyweight(row) for row in cursor.fetchall()]

    def get_latest_bodyweight(self) -> Optional[BodyWeightEntry]:
        """Get the most recent body weight entry."""
        entries = self.get_bodyweight_entries(limit=1)
        return entries[0] if entries else None

    def save_activity(self, entry: DailyActivityEntry) -> str:
        """Save a daily activity entry."""
        cursor = self.conn.cursor()

        # Serialize activities to JSON
        activities_json = json.dumps(
            [a.model_dump() for a in entry.activities],
            cls=DecimalEncoder,
        ) if entry.activities else None

        cursor.execute(
            """
            INSERT OR REPLACE INTO daily_activity
            (id, date, source, steps, total_calories, active_calories, active_minutes,
             strain, recovery_score, hrv, resting_heart_rate, sleep_hours, sleep_quality,
             exercise_minutes, stand_hours, move_calories, activities_json, notes, raw_ocr_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                entry.id,
                entry.date.isoformat(),
                entry.source.value,
                entry.steps,
                entry.total_calories,
                entry.active_calories,
                entry.active_minutes,
                entry.strain,
                entry.recovery_score,
                entry.hrv,
                entry.resting_heart_rate,
                entry.sleep_hours,
                entry.sleep_quality,
                entry.exercise_minutes,
                entry.stand_hours,
                entry.move_calories,
                activities_json,
                entry.notes,
                entry.raw_ocr_text,
            ),
        )
        self.conn.commit()
        return entry.id

    def get_activity(self, entry_id: str) -> Optional[DailyActivityEntry]:
        """Retrieve an activity entry by ID."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM daily_activity WHERE id = ?",
            (entry_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_activity(row)

    def get_activity_entries(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        source: Optional[ActivitySource] = None,
        limit: Optional[int] = None,
    ) -> list[DailyActivityEntry]:
        """Retrieve activity entries within a date range."""
        cursor = self.conn.cursor()
        query = "SELECT * FROM daily_activity WHERE 1=1"
        params: list = []

        if start_date:
            query += " AND date >= ?"
            params.append(start_date.isoformat())
        if end_date:
            query += " AND date <= ?"
            params.append(end_date.isoformat())
        if source:
            query += " AND source = ?"
            params.append(source.value)

        query += " ORDER BY date DESC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        cursor.execute(query, params)
        return [self._row_to_activity(row) for row in cursor.fetchall()]

    def get_latest_activity(self) -> Optional[DailyActivityEntry]:
        """Get the most recent activity entry."""
        entries = self.get_activity_entries(limit=1)
        return entries[0] if entries else None

    def save_program_block(self, block: ProgramBlock) -> str:
        """Save a program block."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO program_blocks
            (id, name, start_date, end_date, primary_goal, secondary_goal,
             weekly_frequency, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                block.id,
                block.name,
                block.start_date.isoformat(),
                block.end_date.isoformat() if block.end_date else None,
                block.primary_goal.value,
                block.secondary_goal.value if block.secondary_goal else None,
                block.weekly_frequency,
                block.notes,
            ),
        )
        self.conn.commit()
        return block.id

    def get_program_block(self, block_id: str) -> Optional[ProgramBlock]:
        """Retrieve a program block by ID."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM program_blocks WHERE id = ?",
            (block_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_program_block(row)

    def get_active_program_block(self) -> Optional[ProgramBlock]:
        """Get the currently active program block."""
        cursor = self.conn.cursor()
        today = date.today().isoformat()
        cursor.execute(
            """
            SELECT * FROM program_blocks
            WHERE start_date <= ? AND (end_date IS NULL OR end_date >= ?)
            ORDER BY start_date DESC LIMIT 1
        """,
            (today, today),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_program_block(row)

    def get_program_blocks(self) -> list[ProgramBlock]:
        """Retrieve all program blocks."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM program_blocks ORDER BY start_date DESC")
        return [self._row_to_program_block(row) for row in cursor.fetchall()]

    def get_exercise_history(
        self,
        exercise_canonical_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[dict]:
        """Get all recorded sets for an exercise."""
        cursor = self.conn.cursor()
        query = """
            SELECT * FROM exercise_sets
            WHERE canonical_id = ? AND is_warmup = 0
        """
        params: list = [exercise_canonical_id]

        if start_date:
            query += " AND session_date >= ?"
            params.append(start_date.isoformat())
        if end_date:
            query += " AND session_date <= ?"
            params.append(end_date.isoformat())

        query += " ORDER BY session_date DESC, set_number"

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_all_exercises(self) -> list[str]:
        """Get list of all exercise canonical IDs in the database."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT DISTINCT canonical_id FROM exercise_sets ORDER BY canonical_id")
        return [row["canonical_id"] for row in cursor.fetchall()]

    def close(self) -> None:
        """Close database connection."""
        self.conn.close()

    def _row_to_session(self, row: sqlite3.Row) -> WorkoutSession:
        """Convert a database row to WorkoutSession."""
        exercises_data = json.loads(row["exercises_json"], object_hook=decimal_hook)
        exercises = []
        for ex_data in exercises_data:
            sets = [SetRecord(**s) for s in ex_data.pop("sets")]
            exercises.append(ExercisePerformance(sets=sets, **ex_data))

        return WorkoutSession(
            id=row["id"],
            date=date.fromisoformat(row["date"]),
            start_time=row["start_time"],
            duration_minutes=row["duration_minutes"],
            exercises=exercises,
            session_rpe=row["session_rpe"],
            notes=row["notes"],
            program_block_id=row["program_block_id"],
            location=row["location"],
        )

    def _row_to_bodyweight(self, row: sqlite3.Row) -> BodyWeightEntry:
        """Convert a database row to BodyWeightEntry."""
        from ..models.bodyweight import MeasurementMethod, TimeOfDay

        return BodyWeightEntry(
            id=row["id"],
            date=date.fromisoformat(row["date"]),
            weight=Decimal(str(row["weight"])),
            weight_unit=WeightUnit(row["weight_unit"]),
            time_of_day=TimeOfDay(row["time_of_day"]) if row["time_of_day"] else None,
            bodyfat_percent=row["bodyfat_percent"],
            measurement_method=(
                MeasurementMethod(row["measurement_method"])
                if row["measurement_method"]
                else None
            ),
            notes=row["notes"],
            is_post_meal=bool(row["is_post_meal"]),
        )

    def _row_to_program_block(self, row: sqlite3.Row) -> ProgramBlock:
        """Convert a database row to ProgramBlock."""
        from ..models.program import TrainingGoal

        return ProgramBlock(
            id=row["id"],
            name=row["name"],
            start_date=date.fromisoformat(row["start_date"]),
            end_date=date.fromisoformat(row["end_date"]) if row["end_date"] else None,
            primary_goal=TrainingGoal(row["primary_goal"]),
            secondary_goal=(
                TrainingGoal(row["secondary_goal"]) if row["secondary_goal"] else None
            ),
            weekly_frequency=row["weekly_frequency"],
            notes=row["notes"],
        )

    def _row_to_activity(self, row: sqlite3.Row) -> DailyActivityEntry:
        """Convert a database row to DailyActivityEntry."""
        activities = []
        if row["activities_json"]:
            activities_data = json.loads(row["activities_json"], object_hook=decimal_hook)
            for a_data in activities_data:
                # Convert activity_type string to enum
                a_data["activity_type"] = CardioWorkoutType(a_data["activity_type"])
                activities.append(CardioActivity(**a_data))

        return DailyActivityEntry(
            id=row["id"],
            date=date.fromisoformat(row["date"]),
            source=ActivitySource(row["source"]),
            steps=row["steps"],
            total_calories=row["total_calories"],
            active_calories=row["active_calories"],
            active_minutes=row["active_minutes"],
            strain=row["strain"],
            recovery_score=row["recovery_score"],
            hrv=row["hrv"],
            resting_heart_rate=row["resting_heart_rate"],
            sleep_hours=row["sleep_hours"],
            sleep_quality=row["sleep_quality"],
            exercise_minutes=row["exercise_minutes"],
            stand_hours=row["stand_hours"],
            move_calories=row["move_calories"],
            activities=activities,
            notes=row["notes"],
            raw_ocr_text=row["raw_ocr_text"],
        )
