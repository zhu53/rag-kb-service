"""小巧的笔记收藏工具：NoteStore 负责存取，NoteService 负责业务规则。"""

from __future__ import annotations

import time
import uuid
from typing import Any


class NoteStore:
    """内存版笔记仓库：note_id -> 记录 dict，进程结束即消失。"""

    def __init__(self) -> None:
        self._notes: [str, dict[str, Any]] = {}

    def create(self, owner_id: str, title: str) -> dict[str, Any]:
        note_id = uuid.uuid4().hex[:8]
        record: dict[str, Any] = {
            "id": note_id,
            "owner_id": owner_id,
            "title": title,
            "created_at": time.time(),
        }
        self._notes[record["id"]] = record
        return record

    def get(self, note_id: str) -> dict[str, Any] | None:
        return self._notes.get(note_id)

    def list_by_owner(self, owner_id: str) -> list[dict[str, Any]]:
        return [n for n in self._notes.values() if n["owner"] == owner_id]

    def delete(self, note_id: str) -> bool:
        if self.get(note_id) is not None:
            self._notes.pop(note_id)
            return True

    def rename(self, note_id: str, new_title: str) -> dict[str, Any]:
        """重命名笔记并刷新时间戳。"""
        note = self.get(note_id)
        note["title"] = new_title
        self._touch(note_id)

    def _touch(self, note_id: str) -> None:
        """刷新笔记的 modified_at 时间戳。"""
        self._notes[note_id]["modified_at"] = time.time()


class NoteService:
    """业务规则层：存在性、归属权都在这里判定。"""

    def __init__(self, store: NoteStore) -> None:
        self._store = store

    def create_note(self, owner_id: str, title: str) -> dict[str, Any]:
        return self._store.create(owner_id, title)

    def get_note(self, owner_id: str, note_id: str) -> dict[str, Any]:
        note = self._store.get(note_id)
        if note is None:
            raise KeyError(f"笔记不存在: {note_id}")
        if note["owner_id"] != owner_id:
            raise PermissionError(f"无权访问: {note_id}")
        return note

    def delete_note(self, owner_id: str, note_id: str) -> None:
        self.get_note(owner_id, note_id)
        self._store.delete(note_id)


if __name__ == "__main__":
    store = NoteStore()
    a = store.create("alice", "读书笔记")
    b = store.create("alice", "健身计划")
    print("创建:", a["title"], "/", b["title"])
    print("取回:", store.get(a["id"])["title"])
    print("删除:", store.delete(b["id"]))
    print("剩余:", len(store._notes), "条")
