"""KBRepository 契约的内存 fake 实现 + 调用账本（spy 手法）。

对照真实现：src/kb_service/repositories/kb_repo.py
契约原则：方法名、参数、返回类型与真 repo 完全一致，只换存储介质（dict）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from kb_service.repositories.rows import KBRow
from kb_service.schemas.kb import KBCreate, KBUpdate


def make_kb_row(kb_id: UUID, owner_id: UUID, *, name: str = "测试库") -> KBRow:
    """造一行完整的 KBRow。

    store 的契约是"完整行"——测试也不能只给半个（只给 owner_id 那种）。
    """
    now = datetime.now(UTC)
    return {
        "id": kb_id,
        "owner_id": owner_id,
        "name": name,
        "description": None,
        "doc_count": 0,
        "created_at": now,
        "updated_at": now,
    }


class FakeKBRepo:
    """有真实行为的测试替身：dict 存取是真逻辑，calls 账本供交互断言。"""

    def __init__(self) -> None:
        self.kbs: dict[UUID, KBRow] = {}
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def _log(self, method: str, args: tuple[Any, ...]) -> None:
        """记账：每笔是 (方法名, 参数元组)，供测试按名字/参数断言。"""
        self.calls.append((method, args))

    def create(self, owner_id: UUID, data: KBCreate) -> KBRow:
        kb_id = uuid4()  # 完整 UUID——KBOut.id: UUID 要求完整格式，短 hex 过不了校验
        now = datetime.now(UTC)
        row: KBRow = {
            "id": kb_id,
            "owner_id": owner_id,
            "name": data.name,
            "description": data.description,  # KBOut 有这个字段，row 必须带上
            "doc_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        self.kbs[kb_id] = row
        self._log("create", (owner_id, data.name))
        return row

    def get(self, kb_id: UUID) -> KBRow | None:
        self._log("get", (kb_id,))
        return self.kbs.get(kb_id)

    def list_by_owner(self, owner_id: UUID, offset: int, limit: int) -> tuple[list[KBRow], int]:
        # 返回 (rows, total) 二元组——service 里是 rows, total = ... 解包
        self._log("list_by_owner", (owner_id, offset, limit))
        rows = [r for r in self.kbs.values() if r["owner_id"] == owner_id]
        rows.sort(key=lambda r: r["created_at"], reverse=True)
        return rows[offset : offset + limit], len(rows)

    def count_by_owner(self, owner_id: UUID) -> int:
        self._log("count_by_owner", (owner_id,))
        return sum(1 for r in self.kbs.values() if r["owner_id"] == owner_id)

    def update(self, kb_id: UUID, data: KBUpdate) -> KBRow | None:
        # service 传的是 KBUpdate 对象（不是 dict），照真 repo 用 model_dump 展开
        self._log("update", (kb_id,))
        row = self.kbs.get(kb_id)
        if row is None:
            return None
        payload = data.model_dump(exclude_unset=True)
        cast("dict[str, Any]", row).update(payload)
        row["updated_at"] = datetime.now(UTC)
        return row

    def delete(self, kb_id: UUID) -> bool:
        self._log("delete", (kb_id,))
        return self.kbs.pop(kb_id, None) is not None

    def incr_doc_count(self, kb_id: UUID, delta: int) -> None:
        self._log("incr_doc_count", (kb_id, delta))
        if row := self.kbs.get(kb_id):
            row["doc_count"] = max(0, row["doc_count"] + delta)
