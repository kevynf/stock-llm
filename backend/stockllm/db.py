from __future__ import annotations

from .repositories import (
    ChatRepository,
    DiagnosticsRepository,
    ResearchRunRepository,
    SettingsRepository,
    WatchlistRepository,
)
from .storage import SQLiteStore, data_dir


class Database(
    SQLiteStore,
    WatchlistRepository,
    SettingsRepository,
    ChatRepository,
    ResearchRunRepository,
    DiagnosticsRepository,
):
    pass
