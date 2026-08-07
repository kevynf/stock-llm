from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from ..market_service import MarketDataUnavailableError, MarketService
from ..models.market import ProviderCheck, StockResearch, StockSearchResult


def create_market_router(service: MarketService) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["market"])

    @router.get("/stocks/search", response_model=list[StockSearchResult])
    def search_stocks(
        q: str = Query(min_length=1, max_length=40),
        data_mode: Literal["demo", "live"] = "live",
    ) -> list[dict]:
        try:
            return service.search(q, data_mode)
        except MarketDataUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.get("/stocks/{code}/research", response_model=StockResearch)
    def stock_research(
        code: str,
        as_of: date = Query(default_factory=date.today),
        data_mode: Literal["demo", "live"] = "live",
    ) -> dict:
        try:
            result = service.research(code, as_of, data_mode)
        except MarketDataUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if not result:
            raise HTTPException(status_code=404, detail="未找到该证券")
        return result

    @router.get("/providers/status", response_model=list[ProviderCheck])
    def provider_status() -> list[dict]:
        return service.provider_status()

    @router.post("/providers/status/check", response_model=list[ProviderCheck])
    def check_provider_status() -> list[dict]:
        return service.check_provider_status()

    return router
