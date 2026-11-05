"""RAG 链路异步测试：单元层直接 await，集成层 AsyncClient + ASGITransport。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from tests.fakes import make_kb_row

from kb_service.main import create_app
from kb_service.repositories.base import store
from kb_service.repositories.rows import DocRow, KBRow
from kb_service.services.rag_service import RagService

USER_ID = UUID("22222222-2222-4222-8222-222222222222")


class FakeDocRepo:
    """doc_repo 契约的内存 fake：list_by_kb 返回 (rows, total)。"""

    def __init__(self, rows: list[DocRow] | None = None) -> None:
        self.rows = rows or []

    def list_by_kb(self, kb_id: UUID, offset: int, limit: int) -> tuple[list[DocRow], int]:
        rows = [r for r in self.rows if r["kb_id"] == kb_id]
        return rows[offset : offset + limit], len(rows)


class FakeKBService:
    """kb_service 的最小替身：鉴权恒通过。"""

    def get_or_403(self, kb_id: UUID, user_id: UUID) -> KBRow:
        return make_kb_row(kb_id, user_id)


def _doc_row(kb_id: UUID, content: str) -> DocRow:
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


async def test_answer_no_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = RagService(doc_repo=FakeDocRepo())
    monkeypatch.setattr(svc, "kb_service", FakeKBService())

    result = await svc.answer(uuid4(), USER_ID, "没有命中任何文档的问题", 3)

    assert result.sources == []
    assert "没有找到" in result.answer


async def test_answer_with_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    kb_id = uuid4()
    repo = FakeDocRepo([_doc_row(kb_id, "RAG 是检索增强生成，先检索再生成。")])
    svc = RagService(doc_repo=repo)
    monkeypatch.setattr(svc, "kb_service", FakeKBService())

    result = await svc.answer(kb_id, USER_ID, "什么是 RAG？", 3)

    assert result.sources
    assert "RAG 是检索增强生成" in result.answer


async def test_answer_stream_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    kb_id = uuid4()
    repo = FakeDocRepo([_doc_row(kb_id, "RAG 是检索增强生成，先检索再生成。")])
    svc = RagService(doc_repo=repo)
    monkeypatch.setattr(svc, "kb_service", FakeKBService())

    chunks = [c async for c in svc.answer_stream(kb_id, USER_ID, "什么是 RAG？", 3)]

    assert chunks
    assert any("data: " in c for c in chunks)
    assert chunks[-1] == "data: [DONE]\n\n"


async def test_chat_sse_via_async_client(
    app: FastAPI,
    override_current_user_id: UUID,
) -> None:
    """集成：先在 store 里种一个 kb + 一篇文档，再走真实路由。"""

    kb_id = uuid4()
    doc_id = uuid4()
    now = datetime.now(UTC)

    # 按 KBOut / doc row 的字段造数据；owner 必须是"当前登录用户"，否则路由里 get_or_403 会拒
    store.kbs[kb_id] = {
        "id": kb_id,
        "owner_id": override_current_user_id,
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
        store.kbs.pop(kb_id, None)
        store.docs.pop(doc_id, None)


async def test_chat_requires_auth(async_client: AsyncClient) -> None:
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
