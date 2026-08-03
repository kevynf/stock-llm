from __future__ import annotations

import json
import logging
import os
import platform
import re
import shutil
import threading
import traceback
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from io import BytesIO
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Iterator, Literal

from .db import Database, data_dir


APP_VERSION = "0.1.0"
LOG_MAX_BYTES = 2 * 1024 * 1024
LOG_BACKUP_COUNT = 5
StorageScope = Literal["market", "external_links", "logs"]

_storage_lock = threading.RLock()
_log_lock = threading.RLock()
_handler: RotatingFileHandler | None = None
_logger = logging.getLogger("stockllm")
_logger.setLevel(logging.INFO)
_logger.propagate = False
_secret_patterns = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"(?i)\b(bearer|api[_ -]?key|authorization|token)\b\s*[:=]?\s*[^\s,;]+"),
)


def _redact_text(value: str) -> str:
    redacted = value
    for pattern in _secret_patterns:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


@contextmanager
def cache_write_lock() -> Iterator[None]:
    with _storage_lock:
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


def storage_paths() -> dict[StorageScope, Path]:
    root = data_dir()
    return {
        "market": root / "cache" / "market",
        "external_links": root / "cache" / "external-links",
        "logs": root / "logs",
    }


def _files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return [item for item in path.rglob("*") if item.is_file()]


def storage_statistics() -> dict:
    labels = {
        "market": "行情缓存",
        "external_links": "外部正文缓存",
        "logs": "日志",
    }
    categories = []
    for scope, path in storage_paths().items():
        files = _files(path)
        categories.append({
            "scope": scope,
            "label": labels[scope],
            "file_count": len(files),
            "bytes": sum(item.stat().st_size for item in files),
        })
    return {
        "categories": categories,
        "temporary_bytes": sum(item["bytes"] for item in categories),
    }


class JsonFormatter(logging.Formatter):
    _reserved = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "component": getattr(record, "component", record.name),
            "event": getattr(record, "event", "message"),
            "message": _redact_text(record.getMessage()[:1000]),
        }
        for key, value in record.__dict__.items():
            if key not in self._reserved and key not in payload and key not in {"args", "exc_info", "exc_text"}:
                payload[key] = _redact_text(value) if isinstance(value, str) else value
        if record.exc_info:
            payload["exception"] = "".join(traceback.format_exception(*record.exc_info))[-8000:]
        return json.dumps(payload, ensure_ascii=False, default=str)


def _new_handler() -> RotatingFileHandler:
    log_dir = storage_paths()["logs"]
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_dir / "stockllm.jsonl",
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT - 1,
        encoding="utf-8",
    )
    handler.setFormatter(JsonFormatter())
    return handler


def configure_logging() -> logging.Logger:
    global _handler
    with _log_lock:
        if _handler is None:
            _handler = _new_handler()
            _logger.addHandler(_handler)
    return _logger


def set_log_level(level: Literal["normal", "detailed"]) -> str:
    configure_logging().setLevel(logging.DEBUG if level == "detailed" else logging.INFO)
    return level


def current_log_level() -> str:
    return "detailed" if _logger.level <= logging.DEBUG else "normal"


def clear_storage(scopes: list[StorageScope]) -> dict:
    global _handler
    unique_scopes = list(dict.fromkeys(scopes))
    paths = storage_paths()
    with cache_write_lock():
        if "logs" in unique_scopes:
            with _log_lock:
                if _handler is not None:
                    _logger.removeHandler(_handler)
                    _handler.close()
                    _handler = None
                shutil.rmtree(paths["logs"], ignore_errors=True)
                configure_logging()
        for scope in unique_scopes:
            if scope == "logs":
                continue
            shutil.rmtree(paths[scope], ignore_errors=True)
            paths[scope].mkdir(parents=True, exist_ok=True)
    return storage_statistics()


def read_logs(limit: int = 200, level: str | None = None) -> list[dict]:
    configure_logging()
    paths = storage_paths()["logs"]
    candidates = sorted(_files(paths), key=lambda item: item.stat().st_mtime, reverse=True)
    entries: list[dict] = []
    for path in candidates:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            continue
        for line in reversed(lines):
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if level and entry.get("level") != level:
                continue
            entries.append(entry)
            if len(entries) >= limit:
                return entries
    return entries


def system_diagnostics(db: Database) -> dict:
    return {
        "app_version": APP_VERSION,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "runtime": "desktop" if os.getenv("STOCKLLM_PACKAGED") == "1" else "browser",
        "data_directory": str(data_dir()),
        "log_level": current_log_level(),
        "storage": storage_statistics(),
        "connections": {
            "model": db.get_setting("model.connection_status", "disconnected"),
            "providers_checked": db.get_setting("providers.last_checked_at", ""),
        },
    }


def _detailed_business_data(db: Database) -> dict:
    with db.connect() as connection:
        runs = [json.loads(row[0]) for row in connection.execute(
            "SELECT payload FROM selection_runs ORDER BY created_at DESC LIMIT 50"
        ).fetchall()]
        chats = [dict(row) for row in connection.execute(
            "SELECT id, created_at, run_id, stock_code FROM chats ORDER BY created_at DESC LIMIT 100"
        ).fetchall()]
        messages = [dict(row) for row in connection.execute(
            "SELECT id, chat_id, role, content, created_at, tool_traces FROM chat_messages "
            "ORDER BY created_at DESC LIMIT 500"
        ).fetchall()]
    return {"research_snapshots": runs, "chats": chats, "messages": messages}


def export_diagnostics(db: Database, detail: Literal["basic", "detailed"]) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "system.json",
            json.dumps(system_diagnostics(db), ensure_ascii=False, indent=2),
        )
        archive.writestr(
            "logs.jsonl",
            "\n".join(json.dumps(item, ensure_ascii=False) for item in read_logs(limit=1000)),
        )
        if detail == "detailed":
            archive.writestr(
                "business-context.json",
                json.dumps(_detailed_business_data(db), ensure_ascii=False, indent=2),
            )
    return buffer.getvalue()


def log_event(level: int, component: str, event: str, message: str, **fields: object) -> None:
    include_exception = bool(fields.pop("exc_info", False))
    configure_logging().log(
        level,
        message,
        extra={"component": component, "event": event, **fields},
        exc_info=include_exception,
    )


configure_logging()
