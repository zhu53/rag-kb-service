from __future__ import annotations

from typing import Any
from uuid import UUID

from kb_service.repositories.base import store
from kb_service.schemas.kb import KBCreate, KBUpdate


class KBRepository:
    """知识库数据访问层。

    W7 TODO：改成 SQLAlchemy 2.0（async session），方法签名保持不变。
    """

    def create(self, owner_id: UUID, data: KBCreate) -> dict[str, Any]:
        kb_id = store.new_id()
        now = store.now()
        row: dict[str, Any] = {
            "id": kb_id,
            "owner_id": owner_id,
            "name": data.name,
            "description": data.description,
            "doc_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        store.kbs[kb_id] = row
        return row

    def get(self, kb_id: UUID) -> dict[str, Any] | None:
        return store.kbs.get(kb_id)

    def list_by_owner(
        self, owner_id: UUID, offset: int, limit: int
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [r for r in store.kbs.values() if r["owner_id"] == owner_id]
        rows.sort(key=lambda r: r["created_at"], reverse=True)
        return rows[offset : offset + limit], len(rows)

    def update(self, kb_id: UUID, data: KBUpdate) -> dict[str, Any] | None:
        row = store.kbs.get(kb_id)
        if row is None:
            return None
        payload = data.model_dump(exclude_unset=True)
        row.update(payload)
        row["updated_at"] = store.now()
        return row

    def delete(self, kb_id: UUID) -> bool:
        return store.kbs.pop(kb_id, None) is not None

    def incr_doc_count(self, kb_id: UUID, delta: int) -> None:
        if row := store.kbs.get(kb_id):
            row["doc_count"] = max(0, row["doc_count"] + delta)
            row["updated_at"] = store.now()
