from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..models.common import BatchDeleteRequest, BatchDeleteResponse, DeleteResponse
from ..models.watchlist import (
    WatchlistCreate,
    WatchlistImportItem,
    WatchlistItem,
    WatchlistUpdate,
)
from ..watchlist_service import (
    WatchlistAlreadyExistsError,
    WatchlistDataUnavailableError,
    WatchlistNotFoundError,
    WatchlistSecurityNotFoundError,
    WatchlistService,
    WatchlistValidationError,
)


def create_watchlist_router(service: WatchlistService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/watchlist", tags=["watchlist"])

    @router.get("", response_model=list[WatchlistItem])
    def list_watchlist() -> list[WatchlistItem]:
        return [WatchlistItem.model_validate(item) for item in service.list_items()]

    @router.post("", response_model=WatchlistItem, status_code=201)
    def add_watchlist(request: WatchlistCreate) -> WatchlistItem:
        try:
            item = service.add_item(request.code, request.note, request.data_mode)
        except WatchlistDataUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except WatchlistSecurityNotFoundError as exc:
            raise HTTPException(status_code=404, detail="未找到该证券，无法加入自选股")
        except WatchlistAlreadyExistsError as exc:
            raise HTTPException(status_code=409, detail="该证券已经在自选股中") from exc
        return WatchlistItem.model_validate(item)

    @router.post("/import", response_model=list[WatchlistItem])
    def import_watchlist(items: list[WatchlistImportItem]) -> list[WatchlistItem]:
        imported = service.import_items([item.model_dump() for item in items])
        return [WatchlistItem.model_validate(item) for item in imported]

    @router.post("/batch-delete", response_model=BatchDeleteResponse)
    def batch_delete_watchlist(request: BatchDeleteRequest) -> BatchDeleteResponse:
        try:
            deleted = service.delete_items(request.ids)
        except WatchlistValidationError as exc:
            raise HTTPException(status_code=422, detail="自选股代码格式不正确")
        except WatchlistNotFoundError as exc:
            raise HTTPException(status_code=404, detail="部分自选股不存在，请刷新后重试")
        return BatchDeleteResponse(deleted=deleted)

    @router.put("/{code}", response_model=WatchlistItem)
    def update_watchlist(code: str, request: WatchlistUpdate) -> WatchlistItem:
        item = service.update_note(code, request.note)
        if not item:
            raise HTTPException(status_code=404, detail="自选股中没有该证券")
        return WatchlistItem.model_validate(item)

    @router.delete("/{code}", response_model=DeleteResponse)
    def delete_watchlist(code: str) -> DeleteResponse:
        if not service.delete_item(code):
            raise HTTPException(status_code=404, detail="自选股中没有该证券")
        return DeleteResponse()

    return router
