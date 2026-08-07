from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from .ai import ModelGateway
from .chat_service import ChatService, SKILLS
from .db import Database
from .engine import STRATEGIES, build_candidates
from .models.chat import ChatCreate, ChatMessageCreate, ChatSession, ChatSummary
from .models.common import SourceMeta
from .models.market import StrategyDefinition
from .models.research import SelectionRun, SelectionRunCreate
from .providers import get_provider


class SelectionRunNotFoundError(LookupError):
    def __init__(self, run_ids: str | list[str]) -> None:
        self.run_ids = [run_ids] if isinstance(run_ids, str) else list(run_ids)
        super().__init__(*self.run_ids)


class SelectionRunInProgressError(RuntimeError):
    def __init__(self, run_ids: list[str]) -> None:
        self.run_ids = list(run_ids)
        super().__init__(*self.run_ids)


class ResearchQueueFullError(RuntimeError):
    def __init__(self, message: str) -> None:
        super().__init__(message)


__all__ = [
    "ResearchQueueFullError",
    "ResearchService",
    "SKILLS",
    "SelectionRunInProgressError",
    "SelectionRunNotFoundError",
]


class ResearchService:
    def __init__(
        self,
        db: Database,
        gateway: ModelGateway | None = None,
        *,
        chat_service: ChatService | None = None,
    ) -> None:
        self.db = db
        self.gateway = gateway if gateway is not None else ModelGateway(db)
        self._chat_service = chat_service if chat_service is not None else ChatService(db, self.gateway)

    @property
    def chat_service(self) -> ChatService:
        return self._chat_service

    def create_chat(self, request: ChatCreate) -> ChatSession:
        return self._chat_service.create_chat(request)

    def get_chat(self, chat_id: str) -> ChatSession | None:
        return self._chat_service.get_chat(chat_id)

    def get_latest_chat(
        self, run_id: str | None = None, stock_code: str | None = None,
    ) -> ChatSession | None:
        return self._chat_service.get_latest_chat(run_id=run_id, stock_code=stock_code)

    def list_chats(self, limit: int = 100) -> list[ChatSummary]:
        return self._chat_service.list_chats(limit)

    def delete_chat(self, chat_id: str) -> bool:
        return self._chat_service.delete_chat(chat_id)

    def delete_chats(self, chat_ids: list[str]) -> int:
        return self._chat_service.delete_chats(chat_ids)

    def add_message(self, chat_id: str, request: ChatMessageCreate) -> ChatSession:
        return self._chat_service.add_message(chat_id, request)

    def prepare_incomplete_runs(self) -> list[tuple[str, SelectionRunCreate]]:
        pending: list[tuple[str, SelectionRunCreate]] = []
        for stored in self.db.list_runs():
            if stored.get("status") not in {"pending", "running"}:
                continue
            request = SelectionRunCreate.model_validate(stored["request"])
            stored["status"] = "pending"
            stored["error"] = None
            provider = stored.get("provider")
            if isinstance(provider, dict):
                provider["status"] = "pending"
            self.db.save_run_and_append_event(
                stored["id"],
                stored["created_at"],
                stored,
                "stage",
                {"stage": "queued", "label": "应用重启后继续任务"},
            )
            pending.append((stored["id"], request))
        return pending

    def list_runs(self) -> list[dict]:
        return self.db.list_runs()

    def strategies(self) -> list[StrategyDefinition]:
        return list(STRATEGIES)

    def get_run(self, run_id: str) -> dict | None:
        return self.db.get_run(run_id)

    def require_run(self, run_id: str) -> dict:
        run = self.get_run(run_id)
        if not run:
            raise SelectionRunNotFoundError(run_id)
        return run

    def get_events_after(self, run_id: str, sequence: int) -> list[dict]:
        return self.db.get_events_after(run_id, sequence)

    def delete_run(self, run_id: str) -> bool:
        return self.db.delete_run(run_id)

    def delete_runs(self, run_ids: list[str]) -> int:
        return self.db.delete_runs(run_ids)

    def delete_run_checked(self, run_id: str) -> None:
        run = self.require_run(run_id)
        if run["status"] in {"pending", "running"}:
            raise SelectionRunInProgressError([run_id])
        if not self.db.delete_run(run_id):
            raise SelectionRunNotFoundError(run_id)

    def delete_runs_checked(self, run_ids: list[str]) -> int:
        unique_ids = list(dict.fromkeys(run_ids))
        runs = {run_id: self.get_run(run_id) for run_id in unique_ids}
        missing = [run_id for run_id, run in runs.items() if not run]
        if missing:
            raise SelectionRunNotFoundError(missing)
        active = [
            run_id for run_id, run in runs.items()
            if run and run["status"] in {"pending", "running"}
        ]
        if active:
            raise SelectionRunInProgressError(active)
        return self.delete_runs(unique_ids)

    def enqueue_run(
        self,
        request: SelectionRunCreate,
        submit_run: Callable[[str, SelectionRunCreate], bool],
    ) -> SelectionRun:
        run = self.start_run(request)
        if submit_run(run.id, request):
            return run
        message = "研究任务队列已满，请稍后重试"
        self.fail_run(run.id, message)
        raise ResearchQueueFullError(message)

    def fail_run(self, run_id: str, message: str) -> None:
        stored = self.db.get_run(run_id)
        if not stored:
            return
        stored["status"] = "failed"
        stored["error"] = message
        provider = stored.get("provider")
        if isinstance(provider, dict):
            provider["status"] = "unavailable"
        self.db.save_run_and_append_event(
            run_id,
            stored["created_at"],
            stored,
            "error",
            {"message": message},
        )

    def start_run(self, request: SelectionRunCreate) -> SelectionRun:
        run_id = str(uuid.uuid4())
        created = datetime.now(timezone.utc)
        run = SelectionRun(
            id=run_id, created_at=created, request=request, status="pending",
            provider=SourceMeta(
                source="等待数据源", as_of=request.as_of,
                fetched_at=created, status="pending",
            ),
            candidate_count=0, excluded_count=0, candidates=[],
            ai_selection=self.gateway.fallback_selection([], "研究任务尚未完成"),
        )
        self.db.save_run_and_append_event(
            run.id,
            run.created_at.isoformat(),
            run.model_dump(mode="json"),
            "stage",
            {"stage": "queued", "label": "任务已创建"},
        )
        return run

    def execute_run(self, run_id: str, request: SelectionRunCreate) -> None:
        stored = self.db.get_run(run_id)
        if not stored:
            return
        created = datetime.fromisoformat(stored["created_at"])
        stored["status"] = "running"
        self.db.save_run_and_append_event(
            run_id,
            stored["created_at"],
            stored,
            "stage",
            {"stage": "preparing", "label": "准备真实数据"},
        )
        try:
            provider = get_provider(request.data_mode)
            rows, source = provider.snapshot(request.as_of)
            self.db.append_event(run_id, "stage", {"stage": "filtering", "label": "执行风险排除"})
            candidates, excluded = build_candidates(rows, request.strategy, source.as_of, source.source)
            self.db.append_event(run_id, "stage", {"stage": "comparing", "label": "比较候选"})
            ai_selection = self.gateway.select(candidates, request)
            run = SelectionRun(
                id=run_id, created_at=created, request=request, status="complete", provider=source,
                candidate_count=len(candidates), excluded_count=len(excluded), candidates=candidates,
                ai_selection=ai_selection,
            )
        except Exception as exc:
            failure_source = SourceMeta(
                source="请求的数据源", as_of=request.as_of,
                fetched_at=datetime.now(timezone.utc), status="unavailable",
            )
            run = SelectionRun(
                id=run_id, created_at=created, request=request, status="failed", provider=failure_source,
                candidate_count=0, excluded_count=0, candidates=[],
                ai_selection=self.gateway.fallback_selection([], str(exc)), error=str(exc),
            )
        payload = run.model_dump(mode="json")
        event_type = "stage" if run.status == "complete" else "error"
        event_payload = (
            {"stage": "complete", "label": "研究完成"}
            if run.status == "complete"
            else {"message": run.error or "研究任务失败"}
        )
        self.db.save_run_and_append_event(
            run.id,
            run.created_at.isoformat(),
            payload,
            event_type,
            event_payload,
        )
