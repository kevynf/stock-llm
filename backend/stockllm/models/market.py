from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from .common import SourceMeta, StrategyId


class StrategyDefinition(BaseModel):
    id: StrategyId
    name: str
    summary: str
    checks: list[str]


class StockSearchResult(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")
    name: str
    sector: str


class ProviderCheck(BaseModel):
    id: str
    provider: str
    name: str
    description: str
    status: Literal["available", "cached", "unavailable"]
    message: str
    checked_at: datetime | None = None


class PriceHistoryPoint(BaseModel):
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


class EvidenceResolutionEntry(BaseModel):
    freshness: Literal["latest", "cached"]
    resolution: Literal["primary", "fallback", "conflict"]
    note: str | None = None


class ResearchNewsItem(BaseModel):
    kind: Literal["新闻", "公告"] | None = None
    content_level: Literal["summary", "title"] | None = None
    title: str
    published_at: date | datetime
    summary: str = ""
    publisher: str | None = None
    url: str | None = None
    source: str | None = None
    channel: str | None = None
    fetched_at: datetime | None = None
    freshness: Literal["latest", "cached"] | None = None


class ContentScope(BaseModel):
    news: str
    notices: str


class StockResearch(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")
    name: str
    sector: str
    price: float
    change_pct: float
    listed_days: int
    suspended: bool
    risk_label: str
    avg_amount_20d: float
    ma20: float
    ma60: float
    return_20d: float
    return_60d: float
    volume_ratio: float
    rsi: float
    pe: float
    roe: float
    profit_growth: float
    revenue_growth: float
    debt_ratio: float
    cashflow_quality: float
    volatility_60d: float
    max_drawdown_60d: float
    history: list[PriceHistoryPoint]
    news: list[ResearchNewsItem]
    source: SourceMeta
    financial_as_of: date | None = None
    financial_published_at: date | None = None
    price_as_of: date | None = None
    price_fetched_at: datetime | None = None
    price_note: str | None = None
    market_as_of: date | None = None
    market_fetched_at: datetime | None = None
    evidence_sources: dict[str, str] = Field(default_factory=dict)
    evidence_resolution: dict[str, EvidenceResolutionEntry] = Field(default_factory=dict)
    content_fetched_at: datetime | None = None
    content_scope: ContentScope | None = None
    content_errors: list[str] = Field(default_factory=list)
