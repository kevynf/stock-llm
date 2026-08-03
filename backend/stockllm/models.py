from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class RiskProfile(StrEnum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    ACTIVE = "active"


class Horizon(StrEnum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class StrategyId(StrEnum):
    TREND = "trend"
    QUALITY = "quality"
    STABILITY = "stability"


class CheckState(StrEnum):
    PASS = "pass"
    CONCERN = "concern"
    FAIL = "fail"


class Recommendation(StrEnum):
    FOLLOW = "follow"
    WAIT = "wait"
    AVOID = "avoid"


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SourceMeta(BaseModel):
    source: str
    as_of: date
    fetched_at: datetime
    status: Literal["pending", "live", "historical", "cached", "demo", "unavailable"]


class StrategyDefinition(BaseModel):
    id: StrategyId
    name: str
    summary: str
    checks: list[str]


class SelectionRunCreate(BaseModel):
    risk_profile: RiskProfile = RiskProfile.BALANCED
    horizon: Horizon = Horizon.MEDIUM
    strategy: StrategyId = StrategyId.TREND
    as_of: date = Field(default_factory=date.today)
    data_mode: Literal["demo", "live"] = "live"


class Evidence(BaseModel):
    id: str
    title: str
    value: str
    source: str
    as_of: date
    fetched_at: datetime | None = None
    freshness: Literal["latest", "cached"] = "latest"
    resolution: Literal["primary", "fallback", "conflict"] = "primary"
    note: str | None = None


class ResearchCheck(BaseModel):
    label: str
    state: CheckState
    reason: str
    evidence_ids: list[str]


class Candidate(BaseModel):
    code: str
    name: str
    sector: str
    price: float
    change_pct: float
    checks: list[ResearchCheck]
    evidence: list[Evidence]
    passed: int
    concerns: int
    completeness: float


class RankedChoice(BaseModel):
    code: str
    name: str
    reason: str
    recommendation: Recommendation
    evidence_ids: list[str]


class AiSelection(BaseModel):
    top_three: list[RankedChoice] = Field(min_length=0, max_length=3)
    preferred_code: str | None
    confidence: Confidence
    watch_conditions: list[str]
    invalidation_signals: list[str]
    data_gaps: list[str]
    summary: str
    status: Literal["complete", "unavailable", "invalid"] = "complete"


class SelectionRun(BaseModel):
    id: str
    created_at: datetime
    request: SelectionRunCreate
    status: Literal["pending", "running", "complete", "failed"]
    provider: SourceMeta
    candidate_count: int
    excluded_count: int
    candidates: list[Candidate]
    ai_selection: AiSelection
    error: str | None = None


class BatchDeleteRequest(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=100)


class StorageClearRequest(BaseModel):
    scopes: list[Literal["market", "external_links", "logs"]] = Field(min_length=1, max_length=3)


class ClientLogInput(BaseModel):
    level: Literal["info", "warning", "error"] = "error"
    event: str = Field(default="client_error", min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=1000)
    location: str | None = Field(default=None, max_length=500)


class LogLevelInput(BaseModel):
    level: Literal["normal", "detailed"]


class DiagnosticsExportInput(BaseModel):
    detail: Literal["basic", "detailed"] = "basic"


class ModelConfigInput(BaseModel):
    base_url: HttpUrl = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    api_key: str | None = Field(default=None, min_length=8)


class ModelConfigView(BaseModel):
    provider: str = "DeepSeek"
    base_url: str
    model: str
    key_configured: bool
    connection_status: Literal["connected", "disconnected"] = "disconnected"


class WatchlistCreate(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")
    note: str = Field(default="", max_length=500)
    data_mode: Literal["demo", "live"] = "live"


class WatchlistUpdate(BaseModel):
    note: str = Field(max_length=500)


class WatchlistImportItem(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")
    name: str = Field(min_length=1, max_length=100)
    note: str = Field(default="", max_length=500)


class WatchlistItem(BaseModel):
    code: str
    name: str
    note: str
    created_at: datetime
    updated_at: datetime


class ChatCreate(BaseModel):
    run_id: str | None = None
    stock_code: str | None = None


class ChatMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    skill: Literal[
        "explain_preferred",
        "compare_top_three",
        "explain_technical",
        "check_fundamental_risk",
        "analyze_news",
        "find_counter_evidence",
        "verify_sources",
        "research_checklist",
    ] = "explain_preferred"


class ChatMessage(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
    tool_traces: list[str] = []


class ChatSession(BaseModel):
    id: str
    run_id: str | None
    stock_code: str | None
    created_at: datetime
    messages: list[ChatMessage] = []


class ChatSummary(BaseModel):
    id: str
    run_id: str | None
    stock_code: str | None
    created_at: datetime
    updated_at: datetime
    message_count: int
    preview: str
