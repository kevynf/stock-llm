from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from . import __version__
from .ai import ModelGateway
from .chat_service import ChatService
from .db import Database
from .diagnostics import log_event
from .market_service import MarketService
from .model_settings_service import ModelSettingsService
from .models.system import HealthResponse
from .routers import (
    create_chat_router,
    create_market_router,
    create_model_settings_router,
    create_research_router,
    create_system_router,
    create_watchlist_router,
)
from .service import ResearchService
from .system_service import SystemService
from .tasks import ResearchTaskRunner
from .watchlist_service import WatchlistService


API_PROTOCOL_VERSION = 1
API_CAPABILITIES = [
    "desktop-session-token",
    "selection-events",
    "system-diagnostics",
]


@dataclass
class ApplicationServices:
    db: Database
    gateway: ModelGateway
    market: MarketService
    watchlist: WatchlistService
    research: ResearchService
    chat: ChatService
    model_settings: ModelSettingsService
    system: SystemService
    runner: ResearchTaskRunner


def create_application_services(database: Database | None = None) -> ApplicationServices:
    db = database if database is not None else Database()
    gateway = ModelGateway(db)
    market = MarketService(db)
    chat = ChatService(db, gateway, market)
    research = ResearchService(db, gateway, chat_service=chat)
    model_settings = ModelSettingsService(db, gateway)
    return ApplicationServices(
        db=db,
        gateway=gateway,
        market=market,
        watchlist=WatchlistService(db),
        research=research,
        chat=chat,
        model_settings=model_settings,
        system=SystemService(db, model_settings.connection_state),
        runner=ResearchTaskRunner(research),
    )


def create_app(services: ApplicationServices | None = None) -> FastAPI:
    dependencies = services if services is not None else create_application_services()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        for run_id, request in dependencies.research.prepare_incomplete_runs():
            if not dependencies.runner.submit(run_id, request):
                dependencies.research.fail_run(run_id, "研究任务队列已满，恢复任务失败")
        try:
            yield
        finally:
            dependencies.runner.shutdown()

    app = FastAPI(title="StockLLM API", version=__version__, lifespan=lifespan)
    app.state.services = dependencies
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://tauri.localhost",
            "https://tauri.localhost",
        ],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
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
            log_event(
                logging.WARNING,
                "api",
                "request",
                "Desktop request rejected",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=401,
            )
            return Response(
                status_code=401,
                content='{"detail":"桌面会话无效，请重新启动应用。"}',
                media_type="application/json",
            )
        try:
            response = await call_next(request)
        except Exception:
            log_event(
                logging.ERROR,
                "api",
                "request_exception",
                "Unhandled request exception",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                exc_info=True,
            )
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

    @app.get("/api/v1/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            version=app.version,
            protocol_version=API_PROTOCOL_VERSION,
            capabilities=API_CAPABILITIES,
        )

    app.include_router(create_market_router(dependencies.market))
    app.include_router(create_watchlist_router(dependencies.watchlist))
    app.include_router(create_model_settings_router(dependencies.model_settings))
    app.include_router(create_system_router(dependencies.system))
    app.include_router(create_research_router(dependencies.research, dependencies.runner.submit))
    app.include_router(create_chat_router(dependencies.chat))

    frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
    return app


_services = create_application_services()
db = _services.db
gateway = _services.gateway
market_service = _services.market
watchlist_service = _services.watchlist
service = _services.research
chat_service = _services.chat
model_settings_service = _services.model_settings
system_service = _services.system
runner = _services.runner
app = create_app(_services)
