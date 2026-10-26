import time
import uuid
from typing import Any


class InMemoryKBRepository:
    """dict 存内存，进程死了数据就没了——最诚实的实现。"""

    def __init__(self) -> None:
        self._data: dict[
            str, dict[str, Any]
        ] = {}  # 存什么结构？提示：kb_id -> 记录dict

    def create(self, owner_id: str, name: str) -> dict[str, Any]:
        kb_id = uuid.uuid4().hex[:8]
        record: dict[str, Any] = {
            "id": kb_id,
            "owner_id": owner_id,
            "name": name,
            "created_at": time.time(),
        }
        self._data[record["id"]] = record
        return record

    def get(self, kb_id: str):
        return self._data.get(kb_id)  # 注意：get 找不到就返回 None，不抛异常

    def list_by_owner(self, owner_id: str):
        # 遍历 self._data.values()，筛 owner_id 匹配的，凑成 list 返回
        return [value for value in self._data.values() if value["owner_id"] == owner_id]

    def delete(self, kb_id: str) -> bool:
        # pop 掉；key 不存在 pop 返回什么？bool 怎么来的？
        if self.get(kb_id) is not None:
            self._data.pop(kb_id)
            return True
        else:
            return False
