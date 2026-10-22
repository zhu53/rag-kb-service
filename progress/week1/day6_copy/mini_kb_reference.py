"""mini_kb_reference.py —— Day6 任务A 的参考实现（照着敲专用）

【怎么用这个文件】
  第 1 档 · 照着敲：新建 mini_kb.py，一行一行抄这份代码。
                  每抄一小段，用嘴念一遍"它在干什么"（念不出来就停下来想）。
  第 2 档 · 背诵：合上这个文件，只看 mini_kb.py，把每个方法的作用讲一遍。
  第 3 档 · 默写：把 mini_kb.py 内容清空，凭记忆重写。卡住最多偷看 3 次，
                  每偷看一次在 day6-抄改记录.md 里记一笔"哪个方法忘了"。

  验收：`python mini_kb.py` 打印 mini_kb: ALL OK

【这份代码与 kb-service 的对应关系】
  InMemoryStore   → repositories/base.py
  KBRepository    → repositories/kb_repo.py
  KBService       → services/kb_service.py
  KBOut           → schemas/kb.py（那里是 pydantic，这里用 dataclass 简化）
"""

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


# 模块级单例。注意这是 Day2 发现过的"坏味道"——W7 会改成每个 Repository 持有 session
store = InMemoryStore()


# ============================================================
# 3. 输出层：对外暴露的对象（数据库行 ≠ 对外对象）
# ============================================================


@dataclass
class KBOut:
    """对外的知识库视图。字段名刻意和数据库行保持一致（owner_id/created_at），
    这样 from_row 不用做名字映射——命名一致能省掉一堆转换代码。"""

    id: UUID
    name: str
    owner_id: UUID
    doc_count: int
    created_at: datetime

    def to_dict(self) -> dict[str, str]:
        """给 API 层用：全部转成字符串，才能 JSON 序列化。"""
        return {
            "id": str(self.id),
            "name": self.name,
            "owner_id": str(self.owner_id),
            "doc_count": str(self.doc_count),
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> KBOut:
        """dict → 对象。这就是 pydantic `model_validate` 的手工版。"""
        return cls(
            id=row["id"],
            name=row["name"],
            owner_id=row["owner_id"],
            doc_count=row["doc_count"],
            created_at=row["created_at"],
        )


# ============================================================
# 4. 数据层：只负责"存取"，不含任何业务规则
# ============================================================


class KBRepository:
    """数据访问层。方法签名要和 kb-service 的 kb_repo.py 一致——
    这样 W7 换成真数据库时，上面的 service 一行都不用改。"""

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


# ============================================================
# 5. 业务层：只做规则判断和对象转换，不碰 store
# ============================================================


class KBService:
    """注意：这个文件里没有 import fastapi —— 换 Web 框架不影响业务规则。"""

    def __init__(self, repo: KBRepository | None = None) -> None:
        # 允许外部注入 repo：测试时可以塞假实现（这叫依赖注入）
        self.repo = repo or KBRepository()

    def create(self, owner_id: UUID, name: str) -> KBOut:
        row = self.repo.create(owner_id, name)
        return KBOut.from_row(row)

    def get_or_403(self, kb_id: UUID, user_id: UUID) -> dict[str, Any]:
        """取一行并校验归属。

        顺序不能反：先查存在（404）再查归属（403）。
        如果反了，"不存在"和"别人的"会返回同一种错误，
        攻击者就能靠状态码差异枚举出哪些 id 真实存在。
        """
        row = self.repo.get(kb_id)
        if row is None:
            raise NotFoundError("知识库不存在")
        if row["owner_id"] != user_id:
            raise ForbiddenError("无权访问该知识库")
        return row

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


# ============================================================
# 6. 自测：6 条断言覆盖增删改查 + 权限
# ============================================================

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
