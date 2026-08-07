from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Literal

from .db import Database
from .diagnostics import (
    clear_storage,
    export_diagnostics,
    log_event,
    read_logs,
    set_log_level,
    storage_statistics,
    system_diagnostics,
)


StorageScope = Literal["market", "external_links", "logs"]
LogLevel = Literal["normal", "detailed"]
ClientLogLevel = Literal["info", "warning", "error"]

__all__ = ["SystemService"]


class SystemService:
    def __init__(
        self,
        db: Database,
        refresh_model_connection: Callable[[], tuple[bool, str]],
    ) -> None:
        self.db = db
        self._refresh_model_connection = refresh_model_connection

    def storage(self) -> dict:
        return storage_statistics()

    def clear_storage(self, scopes: list[StorageScope]) -> dict:
        result = clear_storage(scopes)
        log_event(logging.INFO, "storage", "clear", "Temporary data cleared", scopes=scopes)
        return result

    def diagnostics(self) -> dict:
        self._refresh_model_connection()
        return system_diagnostics(self.db)

    def logs(self, limit: int, level: str | None) -> list[dict]:
        return read_logs(limit=limit, level=level)

    def record_client_log(
        self,
        level: ClientLogLevel,
        event: str,
        message: str,
        location: str | None,
    ) -> None:
        levels = {"info": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR}
        sanitized_location = location.split("?", 1)[0] if location else None
        log_event(levels[level], "frontend", event, message, location=sanitized_location)

    def set_log_level(self, level: LogLevel) -> str:
        return set_log_level(level)

    def export_diagnostics(self, detail: Literal["basic", "detailed"]) -> bytes:
        self._refresh_model_connection()
        return export_diagnostics(self.db, detail)
