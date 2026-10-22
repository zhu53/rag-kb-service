from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

# ============================================================
# 1. 异常层：业务异常。status_code 挂在自己身上，API 层用它翻译成 HTTP 状态码
# ============================================================


class NotFoundError(Exception):
    """资源不存在 → 404"""

    status_code = 404


class ForbiddenError(Exception):
    """没有权限 → 403"""

    status_code = 403


# ============================================================
# 2. 存储层：假装这是一个数据库
# ============================================================


class InMemoryStore:
    """内存存储。W7 换成 SQLAlchemy 的 async session 后，这一层就消失了。"""

    def __init__(self) -> None:
        # key 是 UUID，value 是"一行数据"（用 dict 模拟数据库的行）
        self.kbs: dict[UUID, dict[str, Any]] = {}
        # 只用来保证 now() 单调递增，见下面 now() 的注释
        self._last_ts: datetime | None = None

    def new_id(self) -> UUID:
        return uuid4()

    def now(self) -> datetime:
        # 必须带 UTC：否则两台时区不同的服务器写进去的时间没法比较
        ts = datetime.now(UTC)
        # ⚠️ 单调兜底，不能省。
        # Windows + Python 3.11 的 datetime.now() 精度只有 15.6ms
        # （实测：连续 20000 次调用，100% 落在同一个时间戳上），
        # 而两次 create() 只隔约 27µs —— 必然拿到相同时间。
        # 时间相同时 list.sort 是稳定排序 → 退化成插入顺序，
        # "后创建的在前" 就失效了。
        # 真数据库里对应的是 ORDER BY created_at DESC, id DESC（用自增 id 兜底）。
        if self._last_ts is not None and ts <= self._last_ts:
            ts = self._last_ts + timedelta(microseconds=1)
        self._last_ts = ts
        return ts


store = InMemoryStore()

# 3. 输出层：对外暴露的对象（数据库行 ≠ 对外对象）

@dataclass
class KBOut:

    id: UUID
    name: str
    owner_id: UUID
    doc_count: int
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "owner_id": str(self.owner_id),
            "doc_count": self.doc_count,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> KBOut:
        return cls(
            id=row["id"],
            name=row["name"],
            owner_id=row["owner_id"],
            doc_count=row["doc_count"],
            created_at=row["created_at"],
        )


# 4. 数据层：只负责"存取"，不含任何业务规则

class KBRepository:

    def create(self, owner_id: UUID, name: str) -> dict[str, Any]:
        now = store.now()
        row: dict[str, Any] = {
            "id": store.new_id(),
            "owner_id": owner_id,
            "name": name,
            "doc_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        store.kbs[row["id"]] = row
        return row

    def get(self, kb_id: UUID) -> dict[str, Any] | None:
        # 用 .get 而不是 []：查不到返回 None，不抛 KeyError
        return store.kbs.get(kb_id)

    def list_by_owner(
        self, owner_id: UUID, offset: int = 0, limit: int = 20
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [r for r in store.kbs.values() if r["owner_id"] == owner_id]
        rows.sort(key=lambda r: r["created_at"], reverse=True)  # 新的在前
        # 注意：total 是"切片前"的总数，不是当前页的条数
        return rows[offset : offset + limit], len(rows)

    def update(self, kb_id: UUID, name: str) -> dict[str, Any] | None:
        row = store.kbs.get(kb_id)
        if row is None:
            return None
        row["name"] = name
        row["updated_at"] = store.now()
        return row

    def delete(self, kb_id: UUID) -> bool:
        # pop 的第二个参数是"查不到时的默认值"，所以这里既能删也能判断存在
        return store.kbs.pop(kb_id, None) is not None

    def count_by_owner(self, owner_id: UUID) -> int:
        # 只数数，不查列表——W7 会变成 SELECT COUNT(*)
        return sum(1 for r in store.kbs.values() if r["owner_id"] == owner_id)


# 5. 业务层：只做规则判断和对象转换

class KBService:
    """注意：这个文件里没有 import fastapi —— 换 Web 框架不影响业务规则。"""

    def __init__(self, repo: KBRepository | None = None) -> None:
        # 允许外部注入 repo：测试时可以塞假实现（这叫依赖注入）
        self.repo = repo or KBRepository()

    def create(self, owner_id: UUID, name: str) -> KBOut:
        row = self.repo.create(owner_id, name)
        return KBOut.from_row(row)

    def get_or_403(self, kb_id: UUID, user_id: UUID) -> KBOut:
        row = self.repo.get(kb_id)
        if row is None:
            raise NotFoundError("知识库不存在")
        if row["owner_id"] != user_id:
            raise ForbiddenError("无权访问该知识库")
        return KBOut.from_row(row)

    def list(self, owner_id: UUID, page: int = 1, size: int = 20) -> tuple[list[KBOut], int]:
        offset = (page - 1) * size
        rows, total = self.repo.list_by_owner(owner_id, offset, size)
        return [KBOut.from_row(r) for r in rows], total

    def update(self, kb_id: UUID, user_id: UUID, name: str) -> KBOut:
        self.get_or_403(kb_id, user_id)  # 先做权限判断，再动手改
        row = self.repo.update(kb_id, name)
        if row is None:
            raise NotFoundError("知识库不存在")
        return KBOut.from_row(row)

    def delete(self, kb_id: UUID, user_id: UUID) -> None:
        self.get_or_403(kb_id, user_id)
        self.repo.delete(kb_id)

    def count_owned(self, user_id: UUID) -> int:
        return self.repo.count_by_owner(user_id)


# 6. 自测：6 条断言覆盖增删改查 + 权限

if __name__ == "__main__":
    svc = KBService()
    me, other = uuid4(), uuid4()

    # 1. 创建 → 能查到
    kb = svc.create(me, "测试库")
    assert kb.name == "测试库"
    assert svc.get_or_403(kb.id, me)["name"] == "测试库"

    # 2. 别人查 → ForbiddenError（而不是 NotFound，因为资源确实存在）
    try:
        svc.get_or_403(kb.id, other)
        raise AssertionError("应该抛 ForbiddenError")
    except ForbiddenError:
        pass

    # 3. 不存在 → NotFoundError
    try:
        svc.get_or_403(uuid4(), me)
        raise AssertionError("应该抛 NotFoundError")
    except NotFoundError:
        pass

    # 4. list 只返回自己的，且按创建时间倒序
    kb2 = svc.create(me, "第二个库")
    svc.create(other, "别人的库")
    # 先证明两个时间戳真的分得开。否则下面那句排序断言其实在测"插入顺序"，
    # 看起来绿了，实际什么都没验证（2026-10-22 踩过这个坑）。
    assert kb2.created_at > kb.created_at, "两次创建拿到同一时间戳，排序断言失效"
    items, total = svc.list(me)
    assert total == 2, f"应该只有自己的 2 个，实际 {total}"
    assert all(item.owner_id == me for item in items)
    assert items[0].name == "第二个库"  # 后创建的在前

    # 5. update 后名字变了
    updated = svc.update(kb.id, me, "改名了")
    assert updated.name == "改名了"

    # 6. delete 后查不到、count 归零（另一个还在）
    svc.delete(kb.id, me)
    try:
        svc.get_or_403(kb.id, me)
        raise AssertionError("删除后应该 NotFoundError")
    except NotFoundError:
        pass
    assert svc.count_owned(me) == 1

    print("mini_kb: ALL OK")
