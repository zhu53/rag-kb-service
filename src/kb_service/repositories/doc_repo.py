from __future__ import annotations

from typing import Any
from uuid import UUID

from kb_service.repositories.base import store
from kb_service.schemas.doc import DocCreate


class DocRepository:
    """文档数据访问层。W7 TODO：换成 SQLAlchemy。"""

    def create(self, kb_id: UUID, data: DocCreate, *, status: str = "pending") -> dict[str, Any]:
        doc_id = store.new_id()
        now = store.now()
        row: dict[str, Any] = {
            "id": doc_id,
            "kb_id": kb_id,
            "title": data.title,
            "content": data.content,
            "status": status,  # W11 起由 Celery 任务更新为 processing/ready/failed
            "chunk_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        store.docs[doc_id] = row
        return row

    def get(self, doc_id: UUID) -> dict[str, Any] | None:
        return store.docs.get(doc_id)

    def list_by_kb(self, kb_id: UUID, offset: int, limit: int) -> tuple[list[dict[str, Any]], int]:
        rows = [r for r in store.docs.values() if r["kb_id"] == kb_id]
        rows.sort(key=lambda r: r["created_at"], reverse=True)
        return rows[offset : offset + limit], len(rows)

    def delete(self, doc_id: UUID) -> bool:
        return store.docs.pop(doc_id, None) is not None

    def update_status(self, doc_id: UUID, status: str, chunk_count: int | None = None) -> None:
        if row := store.docs.get(doc_id):
            row["status"] = status
            if chunk_count is not None:
                row["chunk_count"] = chunk_count
            row["updated_at"] = store.now()
