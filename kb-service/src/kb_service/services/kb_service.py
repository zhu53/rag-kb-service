from __future__ import annotations

from typing import Any
from uuid import UUID

from kb_service.core.exceptions import ForbiddenError, NotFoundError
from kb_service.repositories.kb_repo import KBRepository
from kb_service.schemas.kb import KBCreate, KBOut, KBUpdate, Page


class KBService:
    """知识库业务逻辑层。

    这里不 import FastAPI、不 import SQLAlchemy —— 换框架/换库都不影响业务规则，
    这是"分层"在面试中最容易讲清楚的价值点。
    """

    def __init__(self, repo: KBRepository | None = None) -> None:
        self.repo = repo or KBRepository()

    def create(self, owner_id: UUID, data: KBCreate) -> KBOut:
        row = self.repo.create(owner_id, data)
        return KBOut.model_validate(row)

    def get_or_403(self, kb_id: UUID, user_id: UUID) -> dict[str, Any]:
        row = self.repo.get(kb_id)
        if row is None:
            raise NotFoundError("知识库不存在")
        if row["owner_id"] != user_id:
            # 注意：这里返回 403 而不是 404，是产品决策。若担心枚举攻击可改 404。
            raise ForbiddenError("无权访问该知识库")
        return row

    def list(self, owner_id: UUID, page: int, size: int) -> Page[KBOut]:
        offset = (page - 1) * size
        rows, total = self.repo.list_by_owner(owner_id, offset, size)
        return Page[KBOut](
            items=[KBOut.model_validate(r) for r in rows],
            total=total,
            page=page,
            size=size,
        )

    def update(self, kb_id: UUID, user_id: UUID, data: KBUpdate) -> KBOut:
        self.get_or_403(kb_id, user_id)
        row = self.repo.update(kb_id, data)
        if row is None:
            raise NotFoundError("知识库不存在")
        return KBOut.model_validate(row)

    def delete(self, kb_id: UUID, user_id: UUID) -> None:
        self.get_or_403(kb_id, user_id)
        self.repo.delete(kb_id)

    def count_owned(self, user_id: UUID) -> int:
        """统计该用户拥有的知识库数量。"""
        return self.repo.count_by_owner(user_id)
