"""RAG 链路异步测试：单元层直接 await，集成层 AsyncClient + ASGITransport。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from kb_service.main import create_app
from kb_service.repositories.base import store
from kb_service.services.rag_service import RagService

USER_ID = UUID("22222222-2222-4222-8222-222222222222")


class FakeDocRepo:
    """doc_repo 契约的内存 fake：list_by_kb 返回 (rows, total)。"""

    def __init__(self, rows: list[dict] | None = None) -> None:
        self.rows = rows or []

    def list_by_kb(self, kb_id: UUID, offset: int, limit: int):
        rows = [r for r in self.rows if r["kb_id"] == kb_id]
        return rows[offset : offset + limit], len(rows)


class FakeKBService:
    """kb_service 的最小替身：鉴权恒通过。"""

    def get_or_403(self, kb_id: UUID, user_id: UUID) -> dict:
        return {"id": kb_id}


def _doc_row(kb_id: UUID, content: str) -> dict:
    now = datetime.now(UTC)
    return {
        "id": uuid4(),
        "kb_id": kb_id,
        "title": "测试文档",
        "content": content,
        "status": "ready",
        "chunk_count": 1,
        "created_at": now,
        "updated_at": now,
    }


@pytest.fixture
async def async_client() -> AsyncIterator[AsyncClient]:
    """集成层客户端：进程内 ASGI，不启端口。"""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_answer_no_sources(monkeypatch):
    svc = RagService(doc_repo=FakeDocRepo())
    monkeypatch.setattr(svc, "kb_service", FakeKBService())

    result = await svc.answer(uuid4(), USER_ID, "没有命中任何文档的问题", 3)

    assert result.sources == []
    assert "没有找到" in result.answer


async def test_answer_with_sources(monkeypatch):
    kb_id = uuid4()
    repo = FakeDocRepo([_doc_row(kb_id, "RAG 是检索增强生成，先检索再生成。")])
    svc = RagService(doc_repo=repo)
    monkeypatch.setattr(svc, "kb_service", FakeKBService())

    result = await svc.answer(kb_id, USER_ID, "什么是 RAG？", 3)

    assert result.sources
    assert "RAG 是检索增强生成" in result.answer


async def test_answer_stream_chunks(monkeypatch):
    kb_id = uuid4()
    repo = FakeDocRepo([_doc_row(kb_id, "RAG 是检索增强生成，先检索再生成。")])
    svc = RagService(doc_repo=repo)
    monkeypatch.setattr(svc, "kb_service", FakeKBService())

    chunks = [c async for c in svc.answer_stream(kb_id, USER_ID, "什么是 RAG？", 3)]

    assert chunks
    assert any("data: " in c for c in chunks)
    assert chunks[-1] == "data: [DONE]\n\n"


async def test_chat_sse_via_async_client(monkeypatch):
    """集成：先在 store 里种一个 kb + 一篇文档，再走真实路由。"""
    app = create_app()

    kb_id = uuid4()
    doc_id = uuid4()
    now = datetime.now(UTC).isoformat()

    # 按 KBOut / doc row 的字段造数据
    store.kbs[kb_id] = {
        "id": kb_id,
        "owner_id": USER_ID,
        "name": "测试库",
        "description": "",
        "doc_count": 1,
        "created_at": now,
        "updated_at": now,
    }

    store.docs[doc_id] = {
        "id": doc_id,
        "kb_id": kb_id,
        "title": "测试文档",
        "content": "RAG 是检索增强生成，先检索再生成。",
        "status": "ready",
        "chunk_count": 1,
        "created_at": now,
        "updated_at": now,
    }

    # 集成层更推荐用 dependency_overrides 覆盖认证依赖，
    # 而不是 monkeypatch 业务对象，因为这样走完整路由栈。
    from kb_service.api.deps import get_current_user_id  # 按你项目的真实路径替换

    async def _fake_user_id():
        return USER_ID

    app.dependency_overrides[get_current_user_id] = _fake_user_id

    try:
        transport = ASGITransport(app=app)
        async with (
            AsyncClient(transport=transport, base_url="http://test") as client,
            client.stream(
                "POST",
                "/api/v1/chat",
                json={
                    "kb_id": str(kb_id),
                    "question": "什么是 RAG？",
                },
            ) as response,
        ):
            lines = [line async for line in response.aiter_lines()]

        assert lines
        assert any("data: " in line for line in lines)
        assert lines[-2] == "data: [DONE]"
    finally:
        app.dependency_overrides.clear()
        store.kbs.pop(kb_id, None)
        store.docs.pop(doc_id, None)


async def test_chat_requires_auth(async_client):
    # 不带 Authorization 头打 /api/v1/chat，断言 401 + code == "UNAUTHORIZED"
    response = await async_client.post(
        "/api/v1/chat",
        json={
            "kb_id": str(uuid4()),
            "question": "什么是 RAG？",
        },
    )

    assert response.status_code == 401
    body = response.json()
    assert body.get("code") == "UNAUTHORIZED"
