"""KBService 单元测试：fake repo，不启 FastAPI、不用 MagicMock。

每个测试 = 一条业务规则。红了一条就知道哪条规则被改坏了。
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from tests.fakes import FakeKBRepo

from kb_service.core.exceptions import ForbiddenError, NotFoundError
from kb_service.schemas.kb import KBCreate, KBUpdate
from kb_service.services.kb_service import KBService

ALICE = uuid4()
BOB = uuid4()


def _calls_named(repo: FakeKBRepo, name: str) -> list:
    """从账本里按方法名过滤——断言'没发生'用这个，不要断言账本全空。"""
    return [c for c in repo.calls if c[0] == name]


def _svc_with_kb(owner: UUID) -> tuple[KBService, FakeKBRepo, UUID]:
    """造一个带 1 个知识库的 service，返回 (service, repo, kb_id)。"""
    repo = FakeKBRepo()
    svc = KBService(repo=repo)
    row = repo.create(owner, KBCreate(name="测试库"))
    repo.calls.clear()  # 清掉 setup 的账，测试只看自己触发的调用
    return svc, repo, row["id"]


def test_create_returns_kbout():
    """create 链路：repo 行 → Pydantic 模型。返回的是 KBOut 对象，用属性访问。"""
    repo = FakeKBRepo()
    svc = KBService(repo=repo)
    out = svc.create(ALICE, KBCreate(name="新库"))
    assert out.name == "新库"
    assert out.owner_id == ALICE
    assert out.doc_count == 0
    assert repo.calls[0] == ("create", (ALICE, "新库"))


def test_missing_kb_raises_not_found():
    """404 规则：查不存在的 id。"""
    svc, repo, _ = _svc_with_kb(ALICE)
    missing = uuid4()
    with pytest.raises(NotFoundError):
        svc.get_or_403(missing, ALICE)
    assert repo.calls[0] == ("get", (missing,))


def test_other_users_kb_raises_forbidden():
    """403 规则：别人的库。

    注意：403 之前 service 必须先 repo.get 看 owner_id——
    所以账本里有且只有一笔 get，不是空的。
    """
    svc, repo, kb_id = _svc_with_kb(ALICE)
    with pytest.raises(ForbiddenError):
        svc.get_or_403(kb_id, BOB)
    assert [c[0] for c in repo.calls] == ["get"]


def test_own_kb_returns_row():
    """正常路径：自己的库原样返回。"""
    svc, repo, kb_id = _svc_with_kb(ALICE)
    row = svc.get_or_403(kb_id, ALICE)
    assert row["id"] == kb_id
    assert row["owner_id"] == ALICE
    assert repo.calls[0] == ("get", (kb_id,))


def test_delete_without_permission_repo_not_called():
    """先鉴权后删除：无权时 ForbiddenError，且 repo.delete 绝不能被调。"""
    svc, repo, kb_id = _svc_with_kb(ALICE)
    with pytest.raises(ForbiddenError):
        svc.delete(kb_id, BOB)
    assert _calls_named(repo, "delete") == []


def test_update_missing_raises_not_found():
    """update 不存在的 id：get_or_403 先抛 404，永远走不到 repo.update。"""
    svc, repo, _ = _svc_with_kb(ALICE)
    with pytest.raises(NotFoundError):
        svc.update(uuid4(), ALICE, KBUpdate(name="新名字"))
    assert _calls_named(repo, "update") == []


def test_list_offset_computed_from_page():
    """分页计算：page=3, size=10 → offset=(3-1)*10=20，参数原样传给 repo。"""
    svc, repo, _ = _svc_with_kb(ALICE)
    svc.list(ALICE, page=3, size=10)
    assert repo.calls[0] == ("list_by_owner", (ALICE, 20, 10))


def test_count_owned_delegates():
    """委托链路：count_owned 只数自己的（BOB 的库不算）。"""
    repo = FakeKBRepo()
    svc = KBService(repo=repo)
    repo.create(ALICE, KBCreate(name="库1"))
    repo.create(ALICE, KBCreate(name="库2"))
    repo.create(BOB, KBCreate(name="别人的库"))
    repo.calls.clear()
    assert svc.count_owned(ALICE) == 2
    assert repo.calls[0] == ("count_by_owner", (ALICE,))
