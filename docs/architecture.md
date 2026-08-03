# Architecture

[English](architecture.md) · [简体中文](architecture.zh-CN.md)

## Boundaries

`frontend` only renders API state. It does not calculate eligibility, research checks, rankings, model prompts, or provider fallback behavior.

`backend/stockllm/engine.py` owns deterministic eligibility and research checklists. `providers.py` owns source normalization and provenance. `ai.py` owns model access and validates that model-selected codes and evidence references remain inside the current run.

SQLite stores transactional metadata and JSON snapshots. Market-history cache adapters may write partitioned Parquet files under the application data directory when a verified live provider is added.

## Trust model

- Provider text and news are untrusted data.
- Model output is untrusted until Pydantic validation and candidate/evidence allow-list checks pass.
- Tool execution is selected by server-owned Skills; the model cannot issue SQL, filesystem, shell, network, MCP, or trading commands.
- Demo data uses a separate, visible mode and is not an automatic fallback for live requests.

## Windows desktop runtime

The Tauri 2 shell launches the PyInstaller API sidecar on a random loopback port, waits for `/api/v1/health`, injects the API origin into the frontend, and terminates the sidecar with the application. Browser development and desktop mode share the same REST/SSE contract.

- A per-launch token is passed through the sidecar environment. JSON requests use `X-StockLLM-Token`; SSE uses a token query parameter only on the event endpoint.
- Packaged data is stored under `%LOCALAPPDATA%\StockLLM`. The NSIS uninstaller does not remove this directory.
- The main window remains hidden until the sidecar health check succeeds. A second instance focuses the existing window.
- `scripts/build-desktop.ps1` produces `packaging/dist/StockLLM_<version>_x64-setup.exe` when the Rust MSVC and Visual C++ toolchains are available.
