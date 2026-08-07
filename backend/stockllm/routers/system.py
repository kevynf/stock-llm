from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from ..models.system import (
    ClientLogInput,
    DiagnosticsExportInput,
    LogEntry,
    LogLevelInput,
    LogLevelView,
    StorageClearRequest,
    StorageStatistics,
    SystemDiagnostics,
)
from ..system_service import SystemService


def create_system_router(service: SystemService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/system", tags=["system"])

    @router.get("/storage", response_model=StorageStatistics)
    def system_storage() -> dict:
        return service.storage()

    @router.post("/storage/clear", response_model=StorageStatistics)
    def system_storage_clear(request: StorageClearRequest) -> dict:
        return service.clear_storage(request.scopes)

    @router.get("/diagnostics", response_model=SystemDiagnostics)
    def diagnostics() -> dict:
        return service.diagnostics()

    @router.get("/logs", response_model=list[LogEntry])
    def logs(limit: int = Query(200, ge=1, le=1000), level: str | None = Query(None)) -> list[dict]:
        if level not in {None, "debug", "info", "warning", "error", "critical"}:
            raise HTTPException(status_code=422, detail="日志级别无效")
        return service.logs(limit, level)

    @router.post("/logs/client", status_code=204)
    def client_log(request: ClientLogInput) -> Response:
        service.record_client_log(request.level, request.event, request.message, request.location)
        return Response(status_code=204)

    @router.post("/log-level", response_model=LogLevelView)
    def log_level(request: LogLevelInput) -> LogLevelView:
        return LogLevelView(level=service.set_log_level(request.level))

    @router.post("/diagnostics/export")
    def diagnostics_export(request: DiagnosticsExportInput) -> Response:
        payload = service.export_diagnostics(request.detail)
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        return Response(
            content=payload,
            media_type="application/zip",
            headers={
                "Content-Disposition":
                    f'attachment; filename="stockllm-diagnostics-{request.detail}-{timestamp}.zip"'
            },
        )

    return router
