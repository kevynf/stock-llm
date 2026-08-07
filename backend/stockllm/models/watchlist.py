from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

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
