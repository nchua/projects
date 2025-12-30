"""Data ingestion modules for fitness tracker imports."""

from .screenshot import (
    ScreenshotExtractionResult,
    extract_from_screenshot,
    detect_source,
)
from .sheets import (
    SheetsClient,
    SheetsConfig,
    SheetsSyncResult,
    get_template,
)

__all__ = [
    # Screenshot
    "ScreenshotExtractionResult",
    "extract_from_screenshot",
    "detect_source",
    # Sheets
    "SheetsClient",
    "SheetsConfig",
    "SheetsSyncResult",
    "get_template",
]
