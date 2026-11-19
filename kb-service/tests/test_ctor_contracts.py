"""构造契约：缺依赖必须当场炸，不能带着 None 往下走三层再炸。

这几条用例保护的是今天（W7-D6）学到的教训：

    早上 A 段零症状，根因是 `KBService(repo)` 少传了 session——
    构造时不报错、创建时不报错、返回 201 也不报错，
    数据却在请求结束时被静默回滚。
    报错点在“用户看不见的地方”，病因在“三层之前的构造函数”。

所以 service 的构造要守住一条不变式：
**要么给 repo，要么给 session；两个都没有，立刻 ValueError。**
"""

from __future__ import annotations

from uuid import UUID

import pytest
from tests.fakes import FakeKBRepo

from kb_service.repositories.rows import DocRow
from kb_service.services.doc_service import DocService
from kb_service.services.rag_service import RagService


class _EmptyDocReader:
    """只实现 DocReader（list_by_kb）的最小桩：RagService 只用这一个方法。"""

    def list_by_kb(self, kb_id: UUID, offset: int, limit: int) -> tuple[list[DocRow], int]:
        return [], 0


def test_doc_service_without_anything_raises() -> None:
    with pytest.raises(ValueError, match="repo 或 session"):
        DocService()


def test_rag_service_without_doc_repo_raises() -> None:
    with pytest.raises(ValueError, match="doc_repo 或 session"):
        RagService(kb_repo=FakeKBRepo())


def test_rag_service_without_kb_repo_raises() -> None:
    with pytest.raises(ValueError, match="kb_repo 或 session"):
        RagService(doc_repo=_EmptyDocReader())


def test_rag_service_with_both_repos_constructs() -> None:
    """两个 repo 都给 → 可以不传 session（纯单元测试路径）。"""
    svc = RagService(doc_repo=_EmptyDocReader(), kb_repo=FakeKBRepo())
    assert svc.doc_repo is not None
