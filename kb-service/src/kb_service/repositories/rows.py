from __future__ import annotations

from datetime import datetime
from typing import TypedDict
from uuid import UUID


class KBRow(TypedDict):
    """kb_service.store 里一行知识库的结构。"""

    id: UUID
    owner_id: UUID
    name: str
    description: str | None
    doc_count: int
    created_at: datetime
    updated_at: datetime


class DocRow(TypedDict):
    """doc_service.store 里一行文档的结构。"""

    id: UUID
    kb_id: UUID
    title: str
    content: str
    status: str
    chunk_count: int
    created_at: datetime
    updated_at: datetime
