from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from .common import CheckState, Confidence, Horizon, Recommendation, RiskProfile, SourceMeta, StrategyId

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
