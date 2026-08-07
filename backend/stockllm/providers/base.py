from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from ..models.common import SourceMeta


class ProviderUnavailable(RuntimeError):
    pass


class ResearchProvider(ABC):
    @abstractmethod
    def snapshot(self, as_of: date) -> tuple[list[dict], SourceMeta]:
        raise NotImplementedError

    @abstractmethod
    def search(self, query: str) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def research(self, code: str, as_of: date) -> dict | None:
        raise NotImplementedError

    @abstractmethod
    def status(self) -> dict:
        raise NotImplementedError
