from __future__ import annotations

from .db import Database
from .providers import get_provider
from .repositories.watchlist import DuplicateWatchlistItemError


class WatchlistAlreadyExistsError(Exception):
    pass


class WatchlistNotFoundError(Exception):
    pass


class WatchlistSecurityNotFoundError(Exception):
    pass


class WatchlistValidationError(Exception):
    pass


class WatchlistDataUnavailableError(RuntimeError):
    """Provider failures translated into the watchlist application boundary."""


__all__ = [
    "WatchlistAlreadyExistsError",
    "WatchlistDataUnavailableError",
    "WatchlistNotFoundError",
    "WatchlistSecurityNotFoundError",
    "WatchlistService",
    "WatchlistValidationError",
]


class WatchlistService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def list_items(self) -> list[dict]:
        return self.db.list_watchlist()

    def add_item(self, code: str, note: str, data_mode: str) -> dict:
        try:
            matches = get_provider(data_mode).search(code)
        except Exception as exc:
            raise WatchlistDataUnavailableError(str(exc)) from exc
        match = next((item for item in matches if item.get("code") == code), None)
        if not match:
            raise WatchlistSecurityNotFoundError
        try:
            return self.db.add_watchlist_item(code, str(match["name"]), note.strip())
        except DuplicateWatchlistItemError as exc:
            raise WatchlistAlreadyExistsError from exc

    def import_items(self, items: list[dict]) -> list[dict]:
        return self.db.import_watchlist(items)

    def delete_items(self, ids: list[str]) -> int:
        codes = list(dict.fromkeys(ids))
        if any(not code.isdigit() or len(code) != 6 for code in codes):
            raise WatchlistValidationError
        existing = {item["code"] for item in self.db.list_watchlist()}
        if any(code not in existing for code in codes):
            raise WatchlistNotFoundError
        return self.db.delete_watchlist_items(codes)

    def update_note(self, code: str, note: str) -> dict | None:
        return self.db.update_watchlist_note(code, note.strip())

    def delete_item(self, code: str) -> bool:
        return self.db.delete_watchlist_item(code)
