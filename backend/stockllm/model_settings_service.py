from __future__ import annotations

from .ai import ModelGateway
from .db import Database
from .models.system import ModelConfigInput, ModelConfigView, ModelTestResponse


MODEL_CONNECTION_STATUS_KEY = "model.connection_status"


class ModelConfigurationError(RuntimeError):
    """Model configuration could not be persisted or stored securely."""


class ModelConnectionError(RuntimeError):
    """The configured model endpoint could not be reached or verified."""


__all__ = ["ModelConfigurationError", "ModelConnectionError", "ModelSettingsService"]


class ModelSettingsService:
    def __init__(self, db: Database, gateway: ModelGateway) -> None:
        self.db = db
        self.gateway = gateway

    def connection_state(self) -> tuple[bool, str]:
        key_configured = bool(self.gateway.get_key())
        connection_status = self.db.get_setting(MODEL_CONNECTION_STATUS_KEY, "disconnected")
        if not key_configured and connection_status != "disconnected":
            connection_status = "disconnected"
            self.db.set_setting(MODEL_CONNECTION_STATUS_KEY, connection_status)
        return key_configured, connection_status

    def get_config(self) -> ModelConfigView:
        config = self.gateway.config()
        key_configured, connection_status = self.connection_state()
        return ModelConfigView(
            base_url=config["base_url"],
            model=config["model"],
            key_configured=key_configured,
            connection_status="connected" if connection_status == "connected" else "disconnected",
        )

    def save_config(self, request: ModelConfigInput) -> ModelConfigView:
        if request.api_key:
            try:
                self.gateway.set_key(request.api_key)
            except Exception as exc:
                raise ModelConfigurationError(str(exc)) from exc
        try:
            self.db.set_setting("model.base_url", str(request.base_url).rstrip("/"))
            self.db.set_setting("model.name", request.model.strip())
            self.db.set_setting(MODEL_CONNECTION_STATUS_KEY, "disconnected")
        except Exception as exc:
            raise ModelConfigurationError(str(exc)) from exc
        return self.get_config()

    def test_connection(self) -> ModelTestResponse:
        try:
            message = self.gateway.test()
        except Exception as exc:
            try:
                self.db.set_setting(MODEL_CONNECTION_STATUS_KEY, "disconnected")
            except Exception as status_error:
                raise ModelConnectionError(str(status_error)) from status_error
            raise ModelConnectionError(str(exc)) from exc
        try:
            self.db.set_setting(MODEL_CONNECTION_STATUS_KEY, "connected")
        except Exception as exc:
            raise ModelConnectionError(str(exc)) from exc
        return ModelTestResponse(message=message)
