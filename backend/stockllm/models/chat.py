from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

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
