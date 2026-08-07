from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


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


class DeleteResponse(BaseModel):
    status: Literal["deleted"] = "deleted"


class BatchDeleteResponse(DeleteResponse):
    deleted: int = Field(ge=0)


class BatchDeleteRequest(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=100)
