from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    protocol_version: int
    capabilities: list[str]


class ModelTestResponse(BaseModel):
    status: Literal["ok"] = "ok"
    message: str


class SkillDefinition(BaseModel):
    id: str
    name: str
    tools: list[str]
    description: str


class StorageCategory(BaseModel):
    scope: Literal["market", "external_links", "logs"]
    label: str
    file_count: int = Field(ge=0)
    bytes: int = Field(ge=0)


class StorageStatistics(BaseModel):
    categories: list[StorageCategory]
    temporary_bytes: int = Field(ge=0)


class LogEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    timestamp: datetime
    level: str
    component: str
    event: str
    message: str
    request_id: str | None = None
    duration_ms: float | None = None
    status_code: int | None = None


class DiagnosticConnections(BaseModel):
    model: Literal["connected", "disconnected"]
    providers_checked: str


class SystemDiagnostics(BaseModel):
    app_version: str
    python_version: str
    platform: str
    architecture: str
    runtime: Literal["browser", "desktop"]
    data_directory: str
    log_level: Literal["normal", "detailed"]
    storage: StorageStatistics
    connections: DiagnosticConnections


class LogLevelView(BaseModel):
    level: Literal["normal", "detailed"]


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
    model: str = "deepseek-v4-flash"
    api_key: str | None = Field(default=None, min_length=8)


class ModelConfigView(BaseModel):
    provider: str = "DeepSeek"
    base_url: str
    model: str
    key_configured: bool
    connection_status: Literal["connected", "disconnected"] = "disconnected"
