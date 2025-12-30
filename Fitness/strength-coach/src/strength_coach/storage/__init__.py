"""Storage backends for strength coach data."""

from .base import StorageBackend
from .sqlite import SQLiteStorage

__all__ = ["StorageBackend", "SQLiteStorage"]
