from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SQLITE_CONNECT_TIMEOUT_SECONDS = 10.0
SQLITE_BUSY_TIMEOUT_MS = 10_000

_temporary_data_lock = threading.RLock()


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


@contextmanager
def cache_write_lock() -> Iterator[None]:
    """Serialize temporary-cache writes across local threads and processes."""
    with _temporary_data_lock:
        lock_path = data_dir() / ".temporary-data.lock"
        with lock_path.open("a+b") as handle:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                if handle.read(1) == b"":
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def atomic_cache_write(path: Path) -> Iterator[Path]:
    """Yield a temporary cache path and replace the target only after a full write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    with cache_write_lock():
        try:
            yield temporary
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def read_json_cache(path: Path) -> dict | None:
    """Return a valid JSON object from a cache, treating corruption as a miss."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


class SQLiteStore:
    SCHEMA_VERSION = 1

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or data_dir() / "stockllm.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=SQLITE_CONNECT_TIMEOUT_SECONDS)
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
        except BaseException:
            connection.rollback()
            raise
        else:
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
                CREATE TABLE IF NOT EXISTS schema_meta (
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
                CREATE INDEX IF NOT EXISTS idx_run_events_run_sequence
                    ON run_events(run_id, sequence);
                CREATE INDEX IF NOT EXISTS idx_chat_messages_chat_created
                    ON chat_messages(chat_id, created_at);
                """
            )
            version_row = connection.execute(
                "SELECT value FROM schema_meta WHERE key='version'"
            ).fetchone()
            version = int(version_row["value"]) if version_row else 0
            if version > self.SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database schema version {version} is newer than supported version {self.SCHEMA_VERSION}"
                )
            if version < self.SCHEMA_VERSION:
                self._migrate(connection, version)

    def _migrate(self, connection: sqlite3.Connection, version: int) -> None:
        """Apply additive migrations in one transaction before recording the version."""
        if version < 1:
            connection.execute(
                "INSERT INTO schema_meta(key, value) VALUES ('version', ?)",
                (str(self.SCHEMA_VERSION),),
            )
