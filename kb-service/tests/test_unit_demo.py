"""我的第一个单元测试：只测 KBService，不启 FastAPI。"""

from typing import Any
from uuid import UUID, uuid4

import pytest

from kb_service.core.exceptions import ForbiddenError, NotFoundError
from kb_service.services.kb_service import KBService


class FakeRepo:
    """最小 fake：只实现 KBService 用到的 get 方法。"""

    def __init__(self, rows: dict[UUID, dict[str, Any]] | None = None) -> None:
        self.rows = rows or {}

    def get(self, kb_id: UUID) -> dict[str, Any] | None:
        return self.rows.get(kb_id)


def test_missing_kb_raises_not_found() -> None:
    svc = KBService(repo=FakeRepo())  # ← 把 fake 塞进去
    with pytest.raises(NotFoundError):
        svc.get_or_403(uuid4(), uuid4())


def test_other_users_kb_raises_forbidden() -> None:
    alice, bob = uuid4(), uuid4()
    kb_id = uuid4()
    svc = KBService(repo=FakeRepo(rows={kb_id: {"owner_id": alice}}))
    with pytest.raises(ForbiddenError):
        svc.get_or_403(kb_id, bob)
