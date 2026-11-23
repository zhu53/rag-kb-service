from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.orm import Session

from kb_service.core.exceptions import NotFoundError
from kb_service.repositories.models import KnowledgeBase
from kb_service.repositories.rows import KBRow
from kb_service.schemas.kb import KBCreate, KBUpdate


class KBRepository:
    """知识库数据访问层（D1 过渡态）。

    `session` 为 None 时沿用内存实现（service/API 层还在用老构造方式）；
    传入 session 时 `create` 走数据库。D2 会把其余方法全部切过去，那时 session 变必传。
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, owner_id: UUID, data: KBCreate) -> KBRow:
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
        obj = self.session.get(KnowledgeBase, kb_id)  # 主键查，最短路径
        return obj.to_row() if obj else None

    def list_by_owner(self, owner_id: UUID, offset: int, limit: int) -> tuple[list[KBRow], int]:
        stmt = (
            select(KnowledgeBase)
            .where(KnowledgeBase.owner_id == owner_id)
            .order_by(KnowledgeBase.created_at.desc())
        )
        page_stmt = stmt.offset(offset).limit(limit)
        result = self.session.execute(page_stmt)
        rows = [row.to_row() for row in result.scalars().all()]
        count_stmt = (
            select(func.count())
            .select_from(KnowledgeBase)
            .where(KnowledgeBase.owner_id == owner_id)
        )
        total = self.session.scalar(count_stmt)
        return rows, (total or 0)

    def count_by_owner(self, owner_id: UUID) -> int:
        """统计该主人名下知识库数量。W7改成 SELECT COUNT(*)."""
        stmt = (
            select(func.count())
            .select_from(KnowledgeBase)
            .where(KnowledgeBase.owner_id == owner_id)
        )
        count = self.session.execute(stmt).scalar()
        return count or 0

    def update(self, kb_id: UUID, data: KBUpdate) -> KBRow | None:
        obj = self.session.get(KnowledgeBase, kb_id)
        if obj is None:
            return None
        payload = data.model_dump(exclude_unset=True)
        # 不再 `if v is not None` 过滤（债②）：None 是合法值——用户显式清空 description。
        # name=None 在 schema 层已拦成 422，能进到这里的是"真正的更新"。
        for k, v in payload.items():
            setattr(obj, k, v)
        return obj.to_row()

    def delete(self, kb_id: UUID) -> bool:
        obj = self.session.get(KnowledgeBase, kb_id)
        if obj is None:
            return False
        self.session.delete(obj)
        return True

    def incr_doc_count(self, kb_id: UUID, delta: int) -> None:
        """原子自增,kb 不存在抛 NotFoundError。"""
        stmt = (
            update(KnowledgeBase)
            .where(KnowledgeBase.id == kb_id)
            .values(doc_count=KnowledgeBase.doc_count + delta)
        )
        result = cast("CursorResult[Any]", self.session.execute(stmt))
        if result.rowcount == 0:
            raise NotFoundError(f"kb {kb_id} not found")
        self.session.flush()
