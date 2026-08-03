from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path


def _startup_event(stage: str, error_type: str | None = None) -> None:
    data_root = Path(os.getenv("LOCALAPPDATA", Path.home())) / "StockLLM"
    log_path = data_root / "logs" / "desktop-launcher.log"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": "error" if error_type else "info",
            "component": "sidecar",
            "event": "startup",
            "stage": stage,
        }
        if error_type:
            entry["error_type"] = error_type
        with log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _watch_parent() -> None:
    parent_pid = os.getenv("STOCKLLM_PARENT_PID")
    if os.name != "nt" or not parent_pid:
        return

    import ctypes

    synchronize = 0x00100000
    infinite = 0xFFFFFFFF
    handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, int(parent_pid))
    if not handle:
        os._exit(0)
    try:
        ctypes.windll.kernel32.WaitForSingleObject(handle, infinite)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)
    os._exit(0)


def main() -> None:
    _startup_event("entry")
    try:
        import uvicorn

        _startup_event("import_application")
        from .main import app

        _startup_event("application_imported")
        port = int(os.environ["STOCKLLM_PORT"])
        threading.Thread(target=_watch_parent, name="parent-watchdog", daemon=True).start()
        _startup_event("starting_uvicorn")
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=port,
            access_log=False,
            log_config=None,
        )
    except BaseException as exc:
        _startup_event("failed", type(exc).__name__)
        raise


if __name__ == "__main__":
    main()
