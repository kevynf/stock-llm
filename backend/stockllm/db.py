from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


def data_dir() -> Path:
    configured = os.getenv("STOCKLLM_DATA_DIR")
    if configured:
        path = Path(configured)
    elif os.getenv("STOCKLLM_PACKAGED") == "1":
        local_app_data = os.getenv("LOCALAPPDATA")
        path = Path(local_app_data) / "StockLLM" if local_app_data else Path.home() / ".stockllm"
    else:
        path = Path(__file__).resolve().parents[2] / "user_data"
    path.mkdir(parents=True, exist_ok=True)
    return path


class Database:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or data_dir() / "stockllm.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS selection_runs (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS run_events (
                    run_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (run_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    run_id TEXT,
                    stock_code TEXT
                );
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    tool_traces TEXT NOT NULL,
                    FOREIGN KEY(chat_id) REFERENCES chats(id)
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS watchlist (
                    code TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

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
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO watchlist(code, name, note, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (code, name, note, now, now),
            )
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

    def set_setting(self, key: str, value: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def get_setting(self, key: str, default: str) -> str:
        with self.connect() as connection:
            row = connection.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return str(row["value"]) if row else default

    def save_run(self, run_id: str, created_at: str, payload: dict) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO selection_runs(id, created_at, payload) VALUES (?, ?, ?)",
                (run_id, created_at, json.dumps(payload, ensure_ascii=False)),
            )

    def get_run(self, run_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT payload FROM selection_runs WHERE id=?", (run_id,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def find_latest_chat(self, run_id: str | None = None, stock_code: str | None = None) -> dict | None:
        conditions: list[str] = []
        parameters: list[str] = []
        if run_id is not None:
            conditions.append("run_id=?")
            parameters.append(run_id)
        if stock_code is not None:
            conditions.append("stock_code=?")
            parameters.append(stock_code)
        if not conditions:
            return None
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id, created_at, run_id, stock_code FROM chats "
                f"WHERE {' AND '.join(conditions)} ORDER BY created_at DESC, id DESC LIMIT 1",
                parameters,
            ).fetchone()
        return dict(row) if row else None

    def list_chats(self, limit: int = 100) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT c.id, c.created_at, c.run_id, c.stock_code, "
                "COALESCE(MAX(m.created_at), c.created_at) AS updated_at, "
                "COUNT(m.id) AS message_count, "
                "COALESCE((SELECT content FROM chat_messages preview "
                "WHERE preview.chat_id=c.id AND preview.role='user' "
                "ORDER BY preview.created_at, preview.id LIMIT 1), '') AS preview "
                "FROM chats c LEFT JOIN chat_messages m ON m.chat_id=c.id "
                "GROUP BY c.id, c.created_at, c.run_id, c.stock_code "
                "ORDER BY updated_at DESC, c.id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_chat(self, chat_id: str) -> bool:
        with self.connect() as connection:
            connection.execute("DELETE FROM chat_messages WHERE chat_id=?", (chat_id,))
            cursor = connection.execute("DELETE FROM chats WHERE id=?", (chat_id,))
        return cursor.rowcount > 0

    def delete_chats(self, chat_ids: list[str]) -> int:
        placeholders = ",".join("?" for _ in chat_ids)
        with self.connect() as connection:
            connection.execute(
                f"DELETE FROM chat_messages WHERE chat_id IN ({placeholders})",
                chat_ids,
            )
            cursor = connection.execute(
                f"DELETE FROM chats WHERE id IN ({placeholders})",
                chat_ids,
            )
        return cursor.rowcount

    def list_runs(self, limit: int = 50) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM selection_runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def delete_run(self, run_id: str) -> bool:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM chat_messages WHERE chat_id IN "
                "(SELECT id FROM chats WHERE run_id=?)",
                (run_id,),
            )
            connection.execute("DELETE FROM chats WHERE run_id=?", (run_id,))
            connection.execute("DELETE FROM run_events WHERE run_id=?", (run_id,))
            cursor = connection.execute("DELETE FROM selection_runs WHERE id=?", (run_id,))
        return cursor.rowcount > 0

    def delete_runs(self, run_ids: list[str]) -> int:
        placeholders = ",".join("?" for _ in run_ids)
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM chat_messages WHERE chat_id IN "
                f"(SELECT id FROM chats WHERE run_id IN ({placeholders}))",
                run_ids,
            )
            connection.execute(
                f"DELETE FROM chats WHERE run_id IN ({placeholders})",
                run_ids,
            )
            connection.execute(
                f"DELETE FROM run_events WHERE run_id IN ({placeholders})",
                run_ids,
            )
            cursor = connection.execute(
                f"DELETE FROM selection_runs WHERE id IN ({placeholders})",
                run_ids,
            )
        return cursor.rowcount

    def save_events(self, run_id: str, events: list[tuple[str, dict]]) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM run_events WHERE run_id=?", (run_id,))
            connection.executemany(
                "INSERT INTO run_events(run_id, sequence, event_type, payload) VALUES (?, ?, ?, ?)",
                [
                    (run_id, index, event_type, json.dumps(payload, ensure_ascii=False))
                    for index, (event_type, payload) in enumerate(events)
                ],
            )

    def get_events(self, run_id: str) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT sequence, event_type, payload FROM run_events WHERE run_id=? ORDER BY sequence",
                (run_id,),
            ).fetchall()
        return [
            {"sequence": row["sequence"], "type": row["event_type"], "payload": json.loads(row["payload"])}
            for row in rows
        ]

    def append_event(self, run_id: str, event_type: str, payload: dict) -> None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(sequence), -1) + 1 AS sequence FROM run_events WHERE run_id=?",
                (run_id,),
            ).fetchone()
            connection.execute(
                "INSERT INTO run_events(run_id, sequence, event_type, payload) VALUES (?, ?, ?, ?)",
                (run_id, int(row["sequence"]), event_type, json.dumps(payload, ensure_ascii=False)),
            )

    def get_events_after(self, run_id: str, sequence: int) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT sequence, event_type, payload FROM run_events "
                "WHERE run_id=? AND sequence>=? ORDER BY sequence",
                (run_id, sequence),
            ).fetchall()
        return [
            {"sequence": row["sequence"], "type": row["event_type"], "payload": json.loads(row["payload"])}
            for row in rows
        ]
