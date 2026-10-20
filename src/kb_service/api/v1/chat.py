from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from kb_service.api.deps import get_current_user_id
from kb_service.schemas.chat import ChatRequest, ChatResponse
from kb_service.services.rag_service import RagService

router = APIRouter()


@router.post("/chat", response_model=None, summary="知识库问答（支持流式）")
async def chat(
    body: ChatRequest,
    user_id: UUID = Depends(get_current_user_id),
) -> ChatResponse | StreamingResponse:
    svc = RagService()
    if body.stream:
        return StreamingResponse(
            svc.answer_stream(body.kb_id, user_id, body.question, body.top_k),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    return await svc.answer(body.kb_id, user_id, body.question, body.top_k)
