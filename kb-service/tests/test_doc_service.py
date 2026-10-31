"""DocService 单元测试：分页偏移、权限、删除计数、切分边界。

用真实的 InMemory 仓储（KBRepository / DocRepository），它们本身就是"内存 fake"，
不需要再手写一套；conftest 里的 autouse fixture 会保证每个测试从空存储开始。
"""

from __future__ import annotations

from typing import Any, NamedTuple
from uuid import UUID, uuid4

import pytest

from kb_service.core.exceptions import ForbiddenError, NotFoundError
from kb_service.repositories.doc_repo import DocRepository
from kb_service.repositories.kb_repo import KBRepository
from kb_service.schemas.doc import DocCreate
from kb_service.schemas.kb import KBCreate
from kb_service.services.doc_service import DocService, split_text


class SpyDocRepo(DocRepository):
    """额外记下 list_by_kb 收到的 offset / limit。

    为什么不直接断言返回的标题列表？因为 list_by_kb 按 created_at 倒序排，
    而 Windows 上 datetime.now() 精度只有 15.6ms，连建几条文档时间戳常常相同，
    排序结果只是"碰巧稳定"；换到 Linux CI（微秒精度）顺序会反过来。
    断言"传给仓储的 offset 是多少"，与排序无关，任何平台都成立。
    """

    def __init__(self) -> None:
        self.offsets: list[int] = []

    def list_by_kb(self, kb_id: UUID, offset: int, limit: int) -> tuple[list[dict[str, Any]], int]:
        self.offsets.append(offset)
        return super().list_by_kb(kb_id, offset, limit)


class World(NamedTuple):
    kb_repo: KBRepository
    doc_repo: SpyDocRepo
    kb_id: UUID
    owner: UUID
    svc: DocService


@pytest.fixture
def owner() -> UUID:
    return uuid4()


@pytest.fixture
def world(owner: UUID) -> World:
    kb_repo = KBRepository()
    doc_repo = SpyDocRepo()
    kb = kb_repo.create(owner, KBCreate(name="知识库"))
    return World(kb_repo, doc_repo, kb["id"], owner, DocService(repo=doc_repo, kb_repo=kb_repo))


def _add_docs(world: World, count: int) -> None:
    for i in range(1, count + 1):
        world.doc_repo.create(world.kb_id, DocCreate(title=f"文档{i}", content="内容"))


# ---------- list：分页偏移 ----------


def test_list_page2_passes_correct_offset(world: World) -> None:
    """page=2, size=2 → offset 必须是 2，不是 4。"""
    _add_docs(world, 5)

    page = world.svc.list(world.kb_id, world.owner, page=2, size=2)

    assert world.doc_repo.offsets == [2]
    assert page.page == 2
    assert page.size == 2
    assert page.total == 5  # total 是总数，不是本页条数


def test_list_last_page_has_one_item(world: World) -> None:
    """5 条、每页 2 条 → 第 3 页只剩 1 条（offset 算错这里会变成 0 条）。"""
    _add_docs(world, 5)

    assert len(world.svc.list(world.kb_id, world.owner, page=3, size=2).items) == 1


# ---------- get：正常 / 404 / 403 ----------


def test_get_returns_doc(world: World) -> None:
    row = world.doc_repo.create(world.kb_id, DocCreate(title="文档1", content="内容"))

    out = world.svc.get(row["id"], world.owner)

    assert out.id == row["id"]
    assert out.title == "文档1"


def test_get_missing_raises_not_found(world: World) -> None:
    with pytest.raises(NotFoundError):
        world.svc.get(uuid4(), world.owner)


def test_get_other_users_doc_forbidden(world: World) -> None:
    row = world.doc_repo.create(world.kb_id, DocCreate(title="文档1", content="内容"))

    with pytest.raises(ForbiddenError):
        world.svc.get(row["id"], uuid4())  # 别人来读


# ---------- delete：删除 / 计数 -1 / 404 ----------


def test_delete_removes_doc(world: World) -> None:
    row = world.doc_repo.create(world.kb_id, DocCreate(title="文档1", content="内容"))

    world.svc.delete(row["id"], world.owner)

    assert world.doc_repo.get(row["id"]) is None


def test_delete_decrements_doc_count(world: World) -> None:
    """删文档时知识库的 doc_count 必须 -1（写成 +1 这里就红）。"""
    row = world.doc_repo.create(world.kb_id, DocCreate(title="文档1", content="内容"))
    world.kb_repo.incr_doc_count(world.kb_id, 1)
    assert world.kb_repo.get(world.kb_id)["doc_count"] == 1

    world.svc.delete(row["id"], world.owner)

    assert world.kb_repo.get(world.kb_id)["doc_count"] == 0


def test_delete_missing_raises_not_found(world: World) -> None:
    with pytest.raises(NotFoundError):
        world.svc.delete(uuid4(), world.owner)


# ---------- split_text：空白块必须丢弃 ----------


def test_split_text_drops_whitespace_chunks() -> None:
    """350 个实字符 + 450 个空格：后两个窗口全是空白，不该产出空块。"""
    assert split_text("x" * 350 + " " * 450) == ["x" * 350]
