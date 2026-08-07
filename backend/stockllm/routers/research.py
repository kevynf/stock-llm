from __future__ import annotations

import json
import time
from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..models.common import BatchDeleteRequest, BatchDeleteResponse, DeleteResponse
from ..models.market import StrategyDefinition
from ..models.research import SelectionRun, SelectionRunCreate
from ..service import (
    ResearchQueueFullError,
    ResearchService,
    SelectionRunInProgressError,
    SelectionRunNotFoundError,
)


def create_research_router(
    service: ResearchService,
    submit_run: Callable[[str, SelectionRunCreate], bool],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["research"])

    @router.get("/strategies", response_model=list[StrategyDefinition])
    def strategies() -> list[StrategyDefinition]:
        return service.strategies()

    @router.post("/selection-runs", response_model=SelectionRun)
    def create_selection_run(request: SelectionRunCreate) -> SelectionRun:
        try:
            return service.enqueue_run(request, submit_run)
        except ResearchQueueFullError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.get("/selection-runs", response_model=list[SelectionRun])
    def list_selection_runs() -> list[dict]:
        return service.list_runs()

    @router.post("/selection-runs/batch-delete", response_model=BatchDeleteResponse)
    def batch_delete_selection_runs(request: BatchDeleteRequest) -> BatchDeleteResponse:
        try:
            deleted = service.delete_runs_checked(request.ids)
        except SelectionRunNotFoundError:
            raise HTTPException(status_code=404, detail="部分研究记录不存在，请刷新后重试")
        except SelectionRunInProgressError:
            raise HTTPException(status_code=409, detail="所选记录中有研究仍在进行，完成后才能删除")
        return BatchDeleteResponse(deleted=deleted)

    @router.get("/selection-runs/{run_id}", response_model=SelectionRun)
    def get_selection_run(run_id: str) -> dict:
        try:
            return service.require_run(run_id)
        except SelectionRunNotFoundError:
            raise HTTPException(status_code=404, detail="选股任务不存在")

    @router.delete("/selection-runs/{run_id}", response_model=DeleteResponse)
    def delete_selection_run(run_id: str) -> DeleteResponse:
        try:
            service.delete_run_checked(run_id)
        except SelectionRunNotFoundError:
            raise HTTPException(status_code=404, detail="研究记录不存在")
        except SelectionRunInProgressError:
            raise HTTPException(status_code=409, detail="研究仍在进行，完成后才能删除")
        return DeleteResponse()

    @router.get("/selection-runs/{run_id}/events")
    def selection_run_events(run_id: str, request: Request) -> StreamingResponse:
        try:
            service.require_run(run_id)
        except SelectionRunNotFoundError:
            raise HTTPException(status_code=404, detail="选股任务不存在")

        def stream():
            last_event_id = request.headers.get("last-event-id", "").strip()
            try:
                sequence = max(int(last_event_id) + 1, 0) if last_event_id else 0
            except ValueError:
                sequence = 0
            while True:
                events = service.get_events_after(run_id, sequence)
                for event in events:
                    sequence = event["sequence"] + 1
                    yield (
                        f"id: {event['sequence']}\n"
                        f"event: {event['type']}\n"
                        f"data: {json.dumps(event['payload'], ensure_ascii=False)}\n\n"
                    )
                run = service.get_run(run_id)
                if run and run["status"] in {"complete", "failed"} and not events:
                    yield "event: end\ndata: {}\n\n"
                    break
                if not events:
                    yield ": keep-alive\n\n"
                time.sleep(0.5)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router
