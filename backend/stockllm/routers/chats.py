from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, StreamingResponse

from ..models.chat import ChatCreate, ChatMessageCreate, ChatSession, ChatSummary
from ..models.common import BatchDeleteRequest, BatchDeleteResponse
from ..models.system import SkillDefinition
from ..chat_service import ChatNotFoundError, ChatService, ResearchRunNotFoundError


def create_chat_router(service: ChatService) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["chats"])

    @router.get("/skills", response_model=list[SkillDefinition])
    def list_skills() -> list[SkillDefinition]:
        return service.list_skills()

    @router.post("/chats", response_model=ChatSession)
    def create_chat(request: ChatCreate) -> ChatSession:
        try:
            return service.create_chat(request)
        except ResearchRunNotFoundError as exc:
            raise HTTPException(status_code=404, detail="关联的选股任务不存在") from exc

    @router.get("/chats", response_model=list[ChatSummary])
    def list_chats(limit: int = Query(default=100, ge=1, le=500)) -> list[ChatSummary]:
        return service.list_chats(limit)

    @router.post("/chats/batch-delete", response_model=BatchDeleteResponse)
    def delete_chats(request: BatchDeleteRequest) -> BatchDeleteResponse:
        deleted = service.delete_chats(request.ids)
        return BatchDeleteResponse(deleted=deleted)

    @router.get("/chats/latest", response_model=ChatSession | None)
    def get_latest_chat(run_id: str | None = None, stock_code: str | None = None) -> ChatSession | None:
        if not run_id and not stock_code:
            raise HTTPException(status_code=422, detail="必须提供研究记录或股票代码")
        return service.get_latest_chat(run_id=run_id, stock_code=stock_code)

    @router.get("/chats/{chat_id}", response_model=ChatSession)
    def get_chat(chat_id: str) -> ChatSession:
        chat = service.get_chat(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="对话不存在")
        return chat

    @router.delete("/chats/{chat_id}", status_code=204)
    def delete_chat(chat_id: str) -> Response:
        if not service.delete_chat(chat_id):
            raise HTTPException(status_code=404, detail="对话不存在")
        return Response(status_code=204)

    @router.post("/chats/{chat_id}/messages", response_model=ChatSession)
    def add_chat_message(chat_id: str, request: ChatMessageCreate) -> ChatSession:
        try:
            return service.add_message(chat_id, request)
        except ChatNotFoundError as exc:
            raise HTTPException(status_code=404, detail="对话不存在") from exc

    @router.get("/chats/{chat_id}/events")
    def chat_events(chat_id: str) -> StreamingResponse:
        chat = service.get_chat(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="对话不存在")

        def stream():
            for message in chat.messages:
                payload = json.dumps(message.model_dump(mode="json"), ensure_ascii=False)
                yield f"event: message\ndata: {payload}\n\n"
            yield "event: end\ndata: {}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    return router
