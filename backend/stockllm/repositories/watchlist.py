from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from .base import SQLiteRepository


class DuplicateWatchlistItemError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class WatchlistRepository(SQLiteRepository):
    def list_watchlist(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT code, name, note, created_at, updated_at FROM watchlist "
                "ORDER BY created_at, code"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_watchlist_item(self, code: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT code, name, note, created_at, updated_at FROM watchlist WHERE code=?",
                (code,),
            ).fetchone()
        return dict(row) if row else None

    def add_watchlist_item(self, code: str, name: str, note: str) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self.connect() as connection:
                connection.execute(
                    "INSERT INTO watchlist(code, name, note, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (code, name, note, now, now),
                )
        except sqlite3.IntegrityError as exc:
            raise DuplicateWatchlistItemError(code) from exc
        return self.get_watchlist_item(code)  # type: ignore[return-value]

    def import_watchlist(self, items: list[dict]) -> list[dict]:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            connection.executemany(
                "INSERT OR IGNORE INTO watchlist(code, name, note, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                [(item["code"], item["name"], item["note"], now, now) for item in items],
            )
        return self.list_watchlist()

    def update_watchlist_note(self, code: str, note: str) -> dict | None:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE watchlist SET note=?, updated_at=? WHERE code=?",
                (note, now, code),
            )
        return self.get_watchlist_item(code) if cursor.rowcount else None

    def delete_watchlist_item(self, code: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM watchlist WHERE code=?", (code,))
        return cursor.rowcount > 0

    def delete_watchlist_items(self, codes: list[str]) -> int:
        placeholders = ",".join("?" for _ in codes)
        with self.connect() as connection:
            cursor = connection.execute(
                f"DELETE FROM watchlist WHERE code IN ({placeholders})",
                codes,
            )
        return cursor.rowcount
