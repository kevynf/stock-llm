# Architecture

[简体中文](architecture.md) | [English](architecture.en.md)

## Boundaries

`frontend` only renders API state. It does not calculate eligibility, research checks, rankings, model prompts, or provider fallback behavior.

`backend/stockllm/engine.py` owns deterministic eligibility and research checklists. `providers/` owns source normalization and provenance: `base.py` defines the stable contract, `demo.py` isolates development-only sample data, `live.py` implements AKShare and BaoStock market research, `content.py` manages content fetching and caching, `status.py` manages source probes, and the package entry only provides compatibility exports and mode assembly. `ai.py` owns model access and validates that model-selected codes and evidence references remain inside the current run.

AKShare calls are serialized by a process-level lock and retry transient failures once. If the bounded retry still fails, the provider-specific error is preserved instead of fabricating content. This prevents third-party global Pandas and progress state from interfering across concurrent research work.

SQLite stores transactional metadata and JSON snapshots. The live provider writes Parquet market caches under the application data directory; each cache is written to a same-directory temporary file and atomically replaced, while corrupt or schema-incompatible files are treated as misses and fetched again.

## Server layers and task execution

- `main.py` assembles FastAPI through an explicit `ApplicationServices` graph, desktop authentication middleware, and process-level dependencies. `create_app` permits isolated application instances in tests while the module retains the production entry point. `routers/` exposes APIs along system, market, watchlist, model-settings, research-run, and chat boundaries.
- `MarketService` owns provider calls, provider-status caching, and provider diagnostics. `WatchlistService` owns stock validation and all-or-nothing watchlist mutations. `ModelSettingsService` owns model configuration, connection-state transitions, and model health checks. `SystemService` owns temporary-storage, logging, diagnostics, and export orchestration. `ChatService` independently owns conversations, context assembly, model exchange, and the skill catalog; `ResearchService` owns only selection-run lifecycle orchestration, reads, deletion, and event replay, while retaining the historical chat methods through an explicitly composed compatibility proxy. These services do not issue SQL directly. `main.py` shares one `ModelGateway` through `ApplicationServices` and injects it into separate chat and research services. `storage.py` owns the data directory, process-safe cache locking, atomic cache replacement, tolerant JSON-cache reads, connection policy, schema initialization, migrations, explicit commit/rollback behavior, and SQLite lock-wait configuration; `repositories/` separately encapsulate watchlist, settings, chat, research-run, and diagnostic-business-snapshot SQL; `Database` composes those repositories behind a stable facade. A `schema_meta` record versions the database schema, and newer unsupported schemas are rejected.
- `ChatService` reuses the same injected `MarketService` and does not assemble providers directly. Per-stock history, news counts and summaries, external document text, conversation messages, and the final model context each have explicit bounds; application-level document truncation remains visibly marked so the model cannot treat partial content as complete.
- `ResearchTaskRunner` executes research work with bounded workers and a bounded waiting queue. Creating a run returns `pending` immediately, while clients observe progress through REST/SSE. Runs left in `pending` or `running` state are returned to the queue when the sidecar restarts.
- Research events carry increasing SSE `id` values. Reconnecting clients send `Last-Event-ID`, so the server only replays unacknowledged events. A visible run transition and its event are committed in the same SQLite transaction, so a terminal snapshot cannot be observed without its corresponding final event.
- Application services translate provider and persistence failures into application-level errors; routers map those errors to HTTP and do not import provider or engine implementations directly. `ResearchService` also owns strategy listing, queue admission, and checked deletion rules.

## API contract

The backend OpenAPI schema is the single source for frontend API types. `scripts/export-openapi.py` exports the schema, `openapi-typescript` generates `frontend/src/generated/openapi.ts`, and frontend domain types reference the generated Pydantic schemas. Market research, provider health, application health, model configuration, skills, storage, logs, system diagnostics, and batch operations use named response models instead of duplicating response shapes in the frontend. CI regenerates the file and checks its diff to prevent backend/frontend contract drift.

Pydantic contracts are grouped by domain under `models/`: `common.py` contains shared enums and metadata, while `market.py`, `research.py`, `system.py`, `watchlist.py`, and `chat.py` own their corresponding API models. The package entry preserves stable exports, so the internal split does not change existing service imports or OpenAPI schema names.

The FastAPI entry point is limited to lifecycle management, middleware, health checks, router assembly, and static asset mounting. Business endpoints are grouped into `market`, `watchlist`, `model_settings`, `research`, `chats`, and `system` modules; a structural test prevents non-health API handlers from moving back into the entry module.

Routers are transport adapters: they validate request models, call an application service, and map its result or typed error to HTTP. The chat-skill catalog follows the same service boundary. Structural tests also protect the provider/engine dependency boundary, including the rule that cache adapters depend on storage rather than diagnostics.

## Trust model

- Provider text and news are untrusted data.
- Model output is untrusted until Pydantic validation and candidate/evidence allow-list checks pass.
- Tool execution is selected by server-owned Skills; the model cannot issue SQL, filesystem, shell, network, MCP, or trading commands.
- Demo data uses a separate, visible mode and is not an automatic fallback for live requests.

## Windows desktop runtime

The Tauri 2 shell launches the PyInstaller API sidecar on a random loopback port, waits for `/api/v1/health`, injects the API origin into the frontend, and terminates the sidecar with the application. Browser development and desktop mode share the same REST/SSE contract.

- A per-launch token is passed through the sidecar environment. JSON requests use `X-StockLLM-Token`; SSE uses a token query parameter only on the event endpoint.
- The windowed Windows sidecar redirects standard output and error to the null device so third-party progress bars cannot write to invalid handles; application diagnostics continue to use structured rotating logs.
- Packaged data is stored under `%LOCALAPPDATA%\StockLLM`. The NSIS uninstaller does not remove this directory.
- The main window remains hidden until the sidecar health check succeeds. A second instance focuses the existing window.
- With Python 3.12+, Rust MSVC, and the Visual C++ toolchain available, `scripts/build-desktop.ps1 -PreflightOnly` validates the interpreter, packaging dependencies, and Tauri CLI; the full script produces `packaging/dist/StockLLM_<version>_x64-setup.exe`.
- PyInstaller collects runtime submodules only and excludes dependency test, demo, and benchmark trees; the packaged binary is still validated against real AKShare, BaoStock, Parquet, and content calls.
