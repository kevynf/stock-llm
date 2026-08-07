from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..model_settings_service import ModelConfigurationError, ModelConnectionError, ModelSettingsService
from ..models.system import ModelConfigInput, ModelConfigView, ModelTestResponse


def create_model_settings_router(service: ModelSettingsService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/models", tags=["models"])

    @router.get("/config", response_model=ModelConfigView)
    def get_model_config() -> ModelConfigView:
        return service.get_config()

    @router.post("/config", response_model=ModelConfigView)
    def save_model_config(request: ModelConfigInput) -> ModelConfigView:
        try:
            return service.save_config(request)
        except ModelConfigurationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.post("/test", response_model=ModelTestResponse)
    def test_model() -> ModelTestResponse:
        try:
            return service.test_connection()
        except ModelConnectionError as exc:
            raise HTTPException(status_code=503, detail=f"DeepSeek 连接失败：{exc}") from exc

    return router
