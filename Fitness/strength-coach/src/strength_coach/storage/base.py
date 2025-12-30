"""Abstract storage interface."""

from abc import ABC, abstractmethod
from datetime import date
from typing import Optional

from ..models import (
    ActivitySource,
    BodyWeightEntry,
    DailyActivityEntry,
    ProgramBlock,
    WorkoutSession,
)


class StorageBackend(ABC):
    """Abstract interface for data persistence."""

    # Workout sessions
    @abstractmethod
    def save_session(self, session: WorkoutSession) -> str:
        """Save a workout session. Returns the session ID."""
        ...

    @abstractmethod
    def get_session(self, session_id: str) -> Optional[WorkoutSession]:
        """Retrieve a session by ID."""
        ...

    @abstractmethod
    def get_sessions(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: Optional[int] = None,
    ) -> list[WorkoutSession]:
        """Retrieve sessions within a date range."""
        ...

    @abstractmethod
    def delete_session(self, session_id: str) -> bool:
        """Delete a session. Returns True if found and deleted."""
        ...

    # Body weight entries
    @abstractmethod
    def save_bodyweight(self, entry: BodyWeightEntry) -> str:
        """Save a body weight entry. Returns the entry ID."""
        ...

    @abstractmethod
    def get_bodyweight(self, entry_id: str) -> Optional[BodyWeightEntry]:
        """Retrieve a body weight entry by ID."""
        ...

    @abstractmethod
    def get_bodyweight_entries(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: Optional[int] = None,
    ) -> list[BodyWeightEntry]:
        """Retrieve body weight entries within a date range."""
        ...

    @abstractmethod
    def get_latest_bodyweight(self) -> Optional[BodyWeightEntry]:
        """Get the most recent body weight entry."""
        ...

    # Activity entries
    @abstractmethod
    def save_activity(self, entry: DailyActivityEntry) -> str:
        """Save a daily activity entry. Returns the entry ID."""
        ...

    @abstractmethod
    def get_activity(self, entry_id: str) -> Optional[DailyActivityEntry]:
        """Retrieve an activity entry by ID."""
        ...

    @abstractmethod
    def get_activity_entries(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        source: Optional[ActivitySource] = None,
        limit: Optional[int] = None,
    ) -> list[DailyActivityEntry]:
        """Retrieve activity entries within a date range."""
        ...

    @abstractmethod
    def get_latest_activity(self) -> Optional[DailyActivityEntry]:
        """Get the most recent activity entry."""
        ...

    # Program blocks
    @abstractmethod
    def save_program_block(self, block: ProgramBlock) -> str:
        """Save a program block. Returns the block ID."""
        ...

    @abstractmethod
    def get_program_block(self, block_id: str) -> Optional[ProgramBlock]:
        """Retrieve a program block by ID."""
        ...

    @abstractmethod
    def get_active_program_block(self) -> Optional[ProgramBlock]:
        """Get the currently active program block."""
        ...

    @abstractmethod
    def get_program_blocks(self) -> list[ProgramBlock]:
        """Retrieve all program blocks."""
        ...

    # Utility
    @abstractmethod
    def get_exercise_history(
        self,
        exercise_canonical_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[dict]:
        """
        Get all recorded sets for an exercise.
        Returns list of dicts with session info + set data.
        """
        ...

    @abstractmethod
    def get_all_exercises(self) -> list[str]:
        """Get list of all exercise canonical IDs in the database."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Close database connection."""
        ...
