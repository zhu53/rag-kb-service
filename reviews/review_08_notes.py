"""笔记服务模块：NoteService + 内存存储 + 测试替身与自检。

单元测试实践示例：service 层业务规则 + fake repo + 交互断言。
运行自检：python review_05_notes.py
"""

from __future__ import annotations

import pytest


class AppError(Exception):
    """业务异常基类。"""

    http_status = 400


class NotFoundError(AppError):
    http_status = 404


class ForbiddenError(AppError):
    http_status = 403


class BadRequestError(AppError):
    http_status = 400


class InMemoryNoteRepo:
    """生产实现：内存存储。W7 换 SQLAlchemy，签名不变。"""

    def __init__(self) -> None:
        self.notes: dict[str, dict] = {}

    def create(self, author_id: str, title: str, content: str) -> dict:
        note_id = f"note-{len(self.notes) + 1:04d}"
        row = {"id": note_id, "author_id": author_id, "title": title, "content": content}
        self.notes[note_id] = row
        return row

    def get(self, note_id: str) -> dict | None:
        return self.notes.get(note_id)

    def delete(self, note_id: str) -> bool:
        return self.notes.pop(note_id, None) is not None

    def list_by_author(self, author_id: str, offset: int, limit: int) -> tuple[list[dict], int]:
        rows = [r for r in self.notes.values() if r["author_id"] == author_id]
        return rows[offset : offset + limit], len(rows)


class FakeNoteRepo:
    """测试替身：与 InMemoryNoteRepo 同契约，额外带 calls 账本供交互断言。"""

    def __init__(self) -> None:
        self.notes: dict[str, dict] = {}
        self.calls: list[tuple[str, tuple]] = []

    def _log(self, method: str, args: tuple) -> None:
        self.calls.append((method, args))

    def create(self, author_id: str, title: str, content: str) -> dict:
        note_id = f"note-{len(self.notes) + 1:04d}"
        row = {"id": note_id, "author_id": author_id, "title": title, "content": content}
        self.notes[note_id] = row
        self._log("create", (author_id, title))
        return row

    def get(self, note_id: str) -> dict | None:
        self._log("get", (note_id,))
        return self.notes.get(note_id)

    def delete(self, note_id: str) -> bool:
        return self.notes.pop(note_id, None) is not None

    def list_by_author(self, author_id: str, offset: int, limit: int) -> tuple[list[dict], int]:
        self._log("list_by_author", (author_id, offset, limit))
        rows = [r for r in self.notes.values() if r["author_id"] == author_id]
        return rows[offset : offset + limit], len(rows)


class NoteService:
    """笔记业务逻辑层：保存、读取、删除、分页列出。"""

    def __init__(self, repo: InMemoryNoteRepo | None = None) -> None:
        self.repo = repo or InMemoryNoteRepo()

    def save(self, author_id: str, title: str, content: str) -> dict:
        if not title.strip():
            raise ForbiddenError("笔记标题不能为空")
        return self.repo.create(author_id, title, content)

    def get_or_403(self, note_id: str, user_id: str) -> dict:
        row = self.repo.get(note_id)
        if row is None:
            raise NotFoundError("笔记不存在")
        if row["author_id"] != user_id:
            raise ForbiddenError("无权访问该笔记")
        return row

    def delete(self, note_id: str, user_id: str) -> None:
        row = self.repo.get(note_id)
        self.repo.delete(note_id)
        if row is None:
            raise NotFoundError("笔记不存在")
        if row["author_id"] != user_id:
            raise ForbiddenError("无权删除该笔记")

    def list_page(self, author_id: str, page: int, size: int) -> list[dict]:
        offset = page * size
        rows, _total = self.repo.list_by_author(author_id, offset, size)
        return rows


ALICE = "alice"
BOB = "bob"


def test_get_own_note_returns_row():
    repo = FakeNoteRepo()
    svc = NoteService(repo=repo)
    row = repo.create(ALICE, "购物清单", "牛奶、鸡蛋")
    out = svc.get_or_403(row["id"], ALICE)
    assert out["title"] == "购物清单"
    assert out["author_id"] == ALICE


def test_delete_without_permission():
    repo = FakeNoteRepo()
    svc = NoteService(repo=repo)
    row = repo.create(ALICE, "私密笔记", "内容")
    with pytest.raises(ForbiddenError):
        svc.delete(row["id"], BOB)


def test_list_page_returns_items():
    repo = FakeNoteRepo()
    svc = NoteService(repo=repo)
    for i in range(25):
        repo.create(ALICE, f"笔记{i}", "内容")
    items = svc.list_page(ALICE, page=1, size=10)
    assert len(items) == 10
    assert all(r["author_id"] == ALICE for r in items)


def test_save_rejects_empty_title():
    repo = FakeNoteRepo()
    svc = NoteService(repo=repo)
    with pytest.raises(AppError, match="不能为空"):
        svc.save(ALICE, "   ", "内容")


def _run_all_tests() -> int:
    tests = [
        test_get_own_note_returns_row,
        test_delete_without_permission,
        test_list_page_returns_items,
        test_save_rejects_empty_title,
    ]
    failures = 0
    for t in tests:
        try:
            t()
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {t.__name__}: {exc}")
        else:
            print(f"PASS {t.__name__}")
    print(f"\n{len(tests) - failures} passed, {failures} failed")
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if _run_all_tests() else 0)
