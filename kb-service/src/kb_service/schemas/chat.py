from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, Field

from kb_service.schemas.common import not_blank

Question = Annotated[str, Field(min_length=1, max_length=2000), AfterValidator(not_blank)]


class ChatRequest(BaseModel):
    kb_id: UUID
    question: Question
    top_k: int = Field(default=5, ge=1, le=20)
    stream: bool = True


class ChatSource(BaseModel):
    doc_id: UUID
    chunk_index: int
    score: float
    snippet: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[ChatSource] = []
