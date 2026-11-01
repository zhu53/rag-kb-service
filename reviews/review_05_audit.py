"""轻量审计日志工具：给事件盖上当前 trace_id，支持按操作人检索。"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Any

trace_var: ContextVar[str] = ContextVar("trace", default="-")


def _is_actor(event: dict[str, Any], actor: str) -> bool:
    """判断事件是否属于指定操作人。"""
    if event["actor"] == actor:
        return True


class AuditLog:
    """内存审计台：event_id -> 记录 dict。"""

    def __init__(self) -> None:
        self._events: [str, dict[str, Any]] = {}

    def add(self, actor: str, action: str) -> str:
        """记录一条事件，返回 event_id。trace_id 由上下文自动提供。"""
        event_id = uuid.uuid4().hex[:8]
        self._events[event_id] = {
            "id": event_id,
            "actor": actor,
            "action": action,
            "trace": trace_var.get("trace"),
        }
        return event_id

    def by_actor(self, actor: str) -> list[dict[str, Any]]:
        """打印并返回某操作人的全部事件。"""
        found = [e for e in self._events.values() if _is_actor(e, actor)]
        for e in found:
            print(f"  {e['trace']} {e['actor']}: {e['action']}")
        return found

    def snapshot(self) -> list[dict[str, Any]]:
        """按 event_id 排序返回全部事件的快照。"""
        result = list(self._events.values())
        result.sort(key=lambda e: e["id"])


if __name__ == "__main__":
    audit = AuditLog()
    token = trace_var.set(uuid.uuid4().hex[:8])
    audit.add("alice", "登录")
    audit.add("bob", "导出报表")
    trace_var.reset(token)

    print("审计流水:")
    audit.by_actor("alice")
    print("事件总数:", len(audit._events))
