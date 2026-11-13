from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy.orm import Session

from kb_service.repositories.base import store
from kb_service.repositories.models import KnowledgeBase
from kb_service.repositories.rows import KBRow
from kb_service.schemas.kb import KBCreate, KBUpdate


class KBRepository:
    """知识库数据访问层（D1 过渡态）。

    `session` 为 None 时沿用内存实现（service/API 层还在用老构造方式）；
    传入 session 时 `create` 走数据库。D2 会把其余方法全部切过去，那时 session 变必传。
    """

    def __init__(self, session: Session | None = None) -> None:
        self.session = session

    def create(self, owner_id: UUID, data: KBCreate) -> KBRow:
        if self.session is None:
            # ---- 过渡期分支：内存实现，等 D2 之后删掉 ----
            kb_id = store.new_id()
            now = store.now()
            row: KBRow = {
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

        # ---- D1 新增：真正写库 ----
        obj = KnowledgeBase(
            owner_id=owner_id,
            name=data.name,
            description=data.description,
            doc_count=0,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.session.add(obj)
        # flush = 把 INSERT 发出去拿到主键；commit 是 service 层的事，这里不做
        self.session.flush()
        return obj.to_row()

    def get(self, kb_id: UUID) -> KBRow | None:
        return store.kbs.get(kb_id)

    def list_by_owner(self, owner_id: UUID, offset: int, limit: int) -> tuple[list[KBRow], int]:
        rows = [r for r in store.kbs.values() if r["owner_id"] == owner_id]
        rows.sort(key=lambda r: r["created_at"], reverse=True)
        return rows[offset : offset + limit], len(rows)

    def count_by_owner(self, owner_id: UUID) -> int:
        """统计该主人名下知识库数量。W7改成 SELECT COUNT(*)."""
        return sum(1 for r in store.kbs.values() if r["owner_id"] == owner_id)

    def update(self, kb_id: UUID, data: KBUpdate) -> KBRow | None:
        row = store.kbs.get(kb_id)
        if row is None:
            return None
        payload = data.model_dump(exclude_unset=True)
        cast("dict[str, Any]", row).update(payload)
        row["updated_at"] = store.now()
        return row

    def delete(self, kb_id: UUID) -> bool:
        return store.kbs.pop(kb_id, None) is not None

    def incr_doc_count(self, kb_id: UUID, delta: int) -> None:
        if row := store.kbs.get(kb_id):
            row["doc_count"] = max(0, row["doc_count"] + delta)
            row["updated_at"] = store.now()
