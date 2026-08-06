from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .db import Database
from .diagnostics import (
    clear_storage, export_diagnostics, log_event, read_logs,
    set_log_level, storage_statistics, system_diagnostics,
)
from .engine import STRATEGIES
from .models import (
    BatchDeleteRequest, ChatCreate, ChatMessageCreate, ChatSession, ChatSummary, ClientLogInput,
    DiagnosticsExportInput, LogLevelInput, ModelConfigInput, ModelConfigView, StorageClearRequest,
    SelectionRun, SelectionRunCreate, WatchlistCreate, WatchlistImportItem, WatchlistItem, WatchlistUpdate,
)
from .providers import ProviderUnavailable, get_provider
from .service import ResearchService, SKILLS


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


db = Database()
service = ResearchService(db)
app = FastAPI(title="StockLLM API", version="0.1.0", lifespan=lifespan)
API_PROTOCOL_VERSION = 1
API_CAPABILITIES = [
    "desktop-session-token",
    "selection-events",
    "system-diagnostics",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://tauri.localhost", "https://tauri.localhost",
    ],
    allow_credentials=False,
    allow_methods=["*"] ,
    allow_headers=["*"] ,
)


@app.middleware("http")
async def desktop_auth_and_request_log(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    started = time.perf_counter()
    desktop_token = os.getenv("STOCKLLM_DESKTOP_TOKEN")
    supplied_token = request.headers.get("x-stockllm-token")
    if request.url.path.endswith("/events"):
        supplied_token = supplied_token or request.query_params.get("desktop_token")
    if (
        desktop_token
        and request.method != "OPTIONS"
        and request.url.path != "/api/v1/health"
        and supplied_token != desktop_token
    ):
        log_event(logging.WARNING, "api", "request", "Desktop request rejected", request_id=request_id,
                  method=request.method, path=request.url.path, status_code=401)
        return Response(status_code=401, content='{"detail":"桌面会话无效，请重新启动应用。"}', media_type="application/json")
    try:
        response = await call_next(request)
    except Exception:
        log_event(logging.ERROR, "api", "request_exception", "Unhandled request exception",
                  request_id=request_id, method=request.method, path=request.url.path,
                  duration_ms=round((time.perf_counter() - started) * 1000, 2), exc_info=True)
        raise
    response.headers["x-request-id"] = request_id
    log_event(
        logging.INFO,
        "api",
        "request",
        "Request completed",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
        status_code=response.status_code,
    )
    return response


@app.get("/api/v1/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": app.version,
        "protocol_version": API_PROTOCOL_VERSION,
        "capabilities": API_CAPABILITIES,
    }


@app.get("/api/v1/system/storage")
def system_storage() -> dict:
    return storage_statistics()


@app.post("/api/v1/system/storage/clear")
def system_storage_clear(request: StorageClearRequest) -> dict:
    result = clear_storage(request.scopes)
    log_event(logging.INFO, "storage", "clear", "Temporary data cleared", scopes=request.scopes)
    return result


@app.get("/api/v1/system/diagnostics")
def diagnostics() -> dict:
    _model_connection_state()
    return system_diagnostics(db)


@app.get("/api/v1/system/logs")
def logs(limit: int = Query(200, ge=1, le=1000), level: str | None = Query(None)) -> list[dict]:
    if level not in {None, "debug", "info", "warning", "error", "critical"}:
        raise HTTPException(status_code=422, detail="日志级别无效")
    return read_logs(limit=limit, level=level)


@app.post("/api/v1/system/logs/client", status_code=204)
def client_log(request: ClientLogInput) -> Response:
    levels = {"info": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR}
    location = request.location.split("?", 1)[0] if request.location else None
    log_event(levels[request.level], "frontend", request.event, request.message, location=location)
    return Response(status_code=204)


@app.post("/api/v1/system/log-level")
def log_level(request: LogLevelInput) -> dict:
    return {"level": set_log_level(request.level)}


@app.post("/api/v1/system/diagnostics/export")
def diagnostics_export(request: DiagnosticsExportInput) -> Response:
    _model_connection_state()
    payload = export_diagnostics(db, request.detail)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="stockllm-diagnostics-{request.detail}-{timestamp}.zip"'},
    )


@app.get("/api/v1/strategies")
def strategies() -> list[dict]:
    return [strategy.model_dump(mode="json") for strategy in STRATEGIES]


@app.post("/api/v1/selection-runs", response_model=SelectionRun)
def create_selection_run(request: SelectionRunCreate, background_tasks: BackgroundTasks) -> SelectionRun:
    run = service.start_run(request)
    background_tasks.add_task(service.execute_run, run.id, request)
    return run


@app.get("/api/v1/selection-runs", response_model=list[SelectionRun])
def list_selection_runs() -> list[dict]:
    return db.list_runs()


@app.post("/api/v1/selection-runs/batch-delete")
def batch_delete_selection_runs(request: BatchDeleteRequest) -> dict:
    run_ids = list(dict.fromkeys(request.ids))
    runs = {run_id: db.get_run(run_id) for run_id in run_ids}
    missing = [run_id for run_id, run in runs.items() if not run]
    if missing:
        raise HTTPException(status_code=404, detail="部分研究记录不存在，请刷新后重试")
    if any(run["status"] in {"pending", "running"} for run in runs.values() if run):
        raise HTTPException(status_code=409, detail="所选记录中有研究仍在进行，完成后才能删除")
    deleted = db.delete_runs(run_ids)
    return {"status": "deleted", "deleted": deleted}


@app.get("/api/v1/selection-runs/{run_id}", response_model=SelectionRun)
def get_selection_run(run_id: str) -> dict:
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="选股任务不存在")
    return run


@app.delete("/api/v1/selection-runs/{run_id}")
def delete_selection_run(run_id: str) -> dict:
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="研究记录不存在")
    if run["status"] in {"pending", "running"}:
        raise HTTPException(status_code=409, detail="研究仍在进行，完成后才能删除")
    if not db.delete_run(run_id):
        raise HTTPException(status_code=404, detail="研究记录不存在")
    return {"status": "deleted"}


@app.get("/api/v1/selection-runs/{run_id}/events")
def selection_run_events(run_id: str) -> StreamingResponse:
    if not db.get_run(run_id):
        raise HTTPException(status_code=404, detail="选股任务不存在")

    def stream():
        sequence = 0
        while True:
            events = db.get_events_after(run_id, sequence)
            for event in events:
                sequence = event["sequence"] + 1
                yield f"event: {event['type']}\ndata: {json.dumps(event['payload'], ensure_ascii=False)}\n\n"
            run = db.get_run(run_id)
            if run and run["status"] in {"complete", "failed"} and not events:
                yield "event: end\ndata: {}\n\n"
                break
            if not events:
                yield ": keep-alive\n\n"
            time.sleep(0.5)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/v1/stocks/search")
def search_stocks(q: str = Query(min_length=1, max_length=40), data_mode: str = "live") -> list[dict]:
    try:
        return get_provider(data_mode).search(q)
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/v1/stocks/{code}/research")
def stock_research(code: str, as_of: date = Query(default_factory=date.today), data_mode: str = "live") -> dict:
    try:
        result = get_provider(data_mode).research(code, as_of)
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not result:
        raise HTTPException(status_code=404, detail="未找到该证券")
    source = result.get("source") if isinstance(result.get("source"), dict) else {}
    log_event(
        logging.INFO, "providers", "stock_research", "Stock research data loaded",
        data_source=source.get("source"), cache_hit=source.get("status") == "cached", status="success",
    )
    return result


PROVIDER_STATUS_CACHE_KEY = "providers.last_status"
PROVIDER_STATUS_VERSION_KEY = "providers.status_version"
PROVIDER_STATUS_VERSION = "2"


def _check_provider_status() -> list[dict]:
    statuses: list[dict] = []
    try:
        provider = get_provider("live")
        if not hasattr(provider, "source_statuses"):
            raise ProviderUnavailable("真实数据源不支持独立状态检查")
        statuses.extend(provider.source_statuses())
    except ProviderUnavailable as exc:
        statuses.extend([
            {"id": "akshare-sina-spot", "provider": "AKShare", "name": "新浪财经 A 股行情", "description": "全市场最新价格、涨跌幅与成交额", "status": "unavailable", "message": str(exc)},
            {"id": "akshare-eastmoney-news", "provider": "AKShare", "name": "东方财富个股新闻", "description": "个股相关新闻、发布时间、发布机构与原文链接", "status": "unavailable", "message": str(exc)},
            {"id": "akshare-cninfo-notices", "provider": "AKShare", "name": "巨潮资讯公告", "description": "上市公司公告、公告日期与原文链接", "status": "unavailable", "message": str(exc)},
            {"id": "baostock-daily", "provider": "BaoStock", "name": "A 股日线行情", "description": "开盘、最高、最低、收盘、成交量与估值字段", "status": "unavailable", "message": str(exc)},
            {"id": "baostock-industry", "provider": "BaoStock", "name": "行业分类", "description": "证券所属行业", "status": "unavailable", "message": str(exc)},
            {"id": "baostock-financial", "provider": "BaoStock", "name": "已发布财务数据", "description": "盈利、成长、资产负债与现金流数据", "status": "unavailable", "message": str(exc)},
        ])
    return statuses


@app.get("/api/v1/providers/status")
def provider_status() -> list[dict]:
    if db.get_setting(PROVIDER_STATUS_VERSION_KEY, "") != PROVIDER_STATUS_VERSION:
        return []
    try:
        cached = json.loads(db.get_setting(PROVIDER_STATUS_CACHE_KEY, "[]"))
    except json.JSONDecodeError:
        return []
    return cached if isinstance(cached, list) else []


@app.post("/api/v1/providers/status/check")
def check_provider_status() -> list[dict]:
    statuses = _check_provider_status()
    db.set_setting(PROVIDER_STATUS_CACHE_KEY, json.dumps(statuses, ensure_ascii=False))
    db.set_setting(PROVIDER_STATUS_VERSION_KEY, PROVIDER_STATUS_VERSION)
    db.set_setting("providers.last_checked_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    log_event(
        logging.INFO, "providers", "status_check", "Provider status check completed",
        data_sources=sorted({item.get("provider") for item in statuses if item.get("provider")}),
        status="success" if any(item.get("status") != "unavailable" for item in statuses) else "unavailable",
    )
    return statuses


@app.get("/api/v1/watchlist", response_model=list[WatchlistItem])
def list_watchlist() -> list[WatchlistItem]:
    return [WatchlistItem.model_validate(item) for item in db.list_watchlist()]


@app.post("/api/v1/watchlist", response_model=WatchlistItem, status_code=201)
def add_watchlist(request: WatchlistCreate) -> WatchlistItem:
    try:
        matches = get_provider(request.data_mode).search(request.code)
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    match = next((item for item in matches if item.get("code") == request.code), None)
    if not match:
        raise HTTPException(status_code=404, detail="未找到该证券，无法加入自选股")
    try:
        item = db.add_watchlist_item(request.code, str(match["name"]), request.note.strip())
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="该证券已经在自选股中") from exc
    return WatchlistItem.model_validate(item)


@app.post("/api/v1/watchlist/import", response_model=list[WatchlistItem])
def import_watchlist(items: list[WatchlistImportItem]) -> list[WatchlistItem]:
    imported = db.import_watchlist([item.model_dump() for item in items])
    return [WatchlistItem.model_validate(item) for item in imported]


@app.post("/api/v1/watchlist/batch-delete")
def batch_delete_watchlist(request: BatchDeleteRequest) -> dict:
    codes = list(dict.fromkeys(request.ids))
    if any(not code.isdigit() or len(code) != 6 for code in codes):
        raise HTTPException(status_code=422, detail="自选股代码格式不正确")
    existing = {item["code"] for item in db.list_watchlist()}
    if any(code not in existing for code in codes):
        raise HTTPException(status_code=404, detail="部分自选股不存在，请刷新后重试")
    deleted = db.delete_watchlist_items(codes)
    return {"status": "deleted", "deleted": deleted}


@app.put("/api/v1/watchlist/{code}", response_model=WatchlistItem)
def update_watchlist(code: str, request: WatchlistUpdate) -> WatchlistItem:
    item = db.update_watchlist_note(code, request.note.strip())
    if not item:
        raise HTTPException(status_code=404, detail="自选股中没有该证券")
    return WatchlistItem.model_validate(item)


@app.delete("/api/v1/watchlist/{code}")
def delete_watchlist(code: str) -> dict:
    if not db.delete_watchlist_item(code):
        raise HTTPException(status_code=404, detail="自选股中没有该证券")
    return {"status": "deleted"}


MODEL_CONNECTION_STATUS_KEY = "model.connection_status"


def _model_connection_state() -> tuple[bool, str]:
    key_configured = bool(service.gateway.get_key())
    connection_status = db.get_setting(MODEL_CONNECTION_STATUS_KEY, "disconnected")
    if not key_configured and connection_status != "disconnected":
        connection_status = "disconnected"
        db.set_setting(MODEL_CONNECTION_STATUS_KEY, connection_status)
    return key_configured, connection_status


@app.get("/api/v1/models/config", response_model=ModelConfigView)
def get_model_config() -> ModelConfigView:
    config = service.gateway.config()
    key_configured, connection_status = _model_connection_state()
    return ModelConfigView(
        base_url=config["base_url"],
        model=config["model"],
        key_configured=key_configured,
        connection_status="connected" if connection_status == "connected" else "disconnected",
    )


@app.post("/api/v1/models/config", response_model=ModelConfigView)
def save_model_config(request: ModelConfigInput) -> ModelConfigView:
    db.set_setting("model.base_url", str(request.base_url).rstrip("/"))
    db.set_setting("model.name", request.model.strip())
    if request.api_key:
        try:
            service.gateway.set_key(request.api_key)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    db.set_setting(MODEL_CONNECTION_STATUS_KEY, "disconnected")
    return get_model_config()


@app.post("/api/v1/models/test")
def test_model() -> dict:
    try:
        message = service.gateway.test()
        db.set_setting(MODEL_CONNECTION_STATUS_KEY, "connected")
        return {"status": "ok", "message": message}
    except Exception as exc:
        db.set_setting(MODEL_CONNECTION_STATUS_KEY, "disconnected")
        raise HTTPException(status_code=503, detail=f"DeepSeek 连接失败：{exc}") from exc


@app.get("/api/v1/skills")
def list_skills() -> list[dict]:
    return [
        {"id": skill_id, "name": data[0], "tools": data[1], "description": data[2]}
        for skill_id, data in SKILLS.items()
    ]


@app.post("/api/v1/chats", response_model=ChatSession)
def create_chat(request: ChatCreate) -> ChatSession:
    if request.run_id and not db.get_run(request.run_id):
        raise HTTPException(status_code=404, detail="关联的选股任务不存在")
    return service.create_chat(request)


@app.get("/api/v1/chats", response_model=list[ChatSummary])
def list_chats(limit: int = Query(default=100, ge=1, le=500)) -> list[ChatSummary]:
    return service.list_chats(limit)


@app.post("/api/v1/chats/batch-delete")
def delete_chats(request: BatchDeleteRequest) -> dict:
    deleted = service.delete_chats(request.ids)
    return {"status": "ok", "deleted": deleted}


@app.get("/api/v1/chats/latest", response_model=ChatSession | None)
def get_latest_chat(run_id: str | None = None, stock_code: str | None = None) -> ChatSession | None:
    if not run_id and not stock_code:
        raise HTTPException(status_code=422, detail="必须提供研究记录或股票代码")
    return service.get_latest_chat(run_id=run_id, stock_code=stock_code)


@app.get("/api/v1/chats/{chat_id}", response_model=ChatSession)
def get_chat(chat_id: str) -> ChatSession:
    chat = service.get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="对话不存在")
    return chat


@app.delete("/api/v1/chats/{chat_id}", status_code=204)
def delete_chat(chat_id: str) -> Response:
    if not service.delete_chat(chat_id):
        raise HTTPException(status_code=404, detail="对话不存在")
    return Response(status_code=204)


@app.post("/api/v1/chats/{chat_id}/messages", response_model=ChatSession)
def add_chat_message(chat_id: str, request: ChatMessageCreate) -> ChatSession:
    try:
        return service.add_message(chat_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="对话不存在") from exc


@app.get("/api/v1/chats/{chat_id}/events")
def chat_events(chat_id: str) -> StreamingResponse:
    chat = service.get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="对话不存在")

    def stream():
        for message in chat.messages:
            payload = json.dumps(message.model_dump(mode="json"), ensure_ascii=False)
            yield f"event: message\ndata: {payload}\n\n"
        yield "event: end\ndata: {}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
