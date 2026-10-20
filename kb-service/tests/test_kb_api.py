from __future__ import annotations

from fastapi.testclient import TestClient


def test_kb_crud_flow(client: TestClient) -> None:
    # create
    r = client.post("/api/v1/kbs", json={"name": "考研资料", "description": "重邮复试"})
    assert r.status_code == 201, r.text
    kb = r.json()
    assert kb["name"] == "考研资料"
    assert kb["doc_count"] == 0
    kb_id = kb["id"]

    # list
    r = client.get("/api/v1/kbs?page=1&size=10")
    assert r.status_code == 200
    assert r.json()["total"] == 1

    # update
    r = client.patch(f"/api/v1/kbs/{kb_id}", json={"name": "考研资料-v2"})
    assert r.status_code == 200
    assert r.json()["name"] == "考研资料-v2"

    # delete
    r = client.delete(f"/api/v1/kbs/{kb_id}")
    assert r.status_code == 204

    r = client.get(f"/api/v1/kbs/{kb_id}")
    assert r.status_code == 404
    assert r.json()["code"] == "NOT_FOUND"


def test_create_kb_validation_error(client: TestClient) -> None:
    r = client.post("/api/v1/kbs", json={"name": ""})
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"


def test_document_upload_and_chunk(client: TestClient) -> None:
    kb_id = client.post("/api/v1/kbs", json={"name": "kb"}).json()["id"]
    content = "人工智能" * 500

    r = client.post(
        f"/api/v1/kbs/{kb_id}/documents",
        json={"title": "note.md", "content": content},
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["status"] == "ready"
    assert doc["chunk_count"] > 1

    # 知识库的 doc_count 应当同步 +1
    assert client.get(f"/api/v1/kbs/{kb_id}").json()["doc_count"] == 1


def test_chat_returns_sources(client: TestClient) -> None:
    kb_id = client.post("/api/v1/kbs", json={"name": "kb"}).json()["id"]
    client.post(
        f"/api/v1/kbs/{kb_id}/documents",
        json={"title": "a.md", "content": "重庆邮电大学人工智能专业复试经验"},
    )

    r = client.post(
        "/api/v1/chat",
        json={"kb_id": kb_id, "question": "复试经验", "stream": False},
    )
    assert r.status_code == 200
    assert len(r.json()["sources"]) >= 1


def test_chat_stream_sse(client: TestClient) -> None:
    kb_id = client.post("/api/v1/kbs", json={"name": "kb"}).json()["id"]
    client.post(
        f"/api/v1/kbs/{kb_id}/documents",
        json={"title": "a.md", "content": "后端工程能力需要持续练习"},
    )

    with client.stream(
        "POST",
        "/api/v1/chat",
        json={"kb_id": kb_id, "question": "后端", "stream": True},
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = "".join(resp.iter_text())
    assert "data: " in body
    assert "[DONE]" in body


def test_count_kbs(client: TestClient) -> None:
    """统计接口应返回当前用户的知识库数量。"""
    for i in range(3):
        client.post("/api/v1/kbs", json={"name": f"kb-{i}"})

    resp = client.get("/api/v1/kbs/stats/count")

    assert resp.status_code == 200
    assert resp.json() == {"count": 3}


def test_count_kbs_excludes_other_users(client: TestClient) -> None:
    """别人的知识库不该被计入。"""
    from uuid import UUID

    from kb_service.core.security import create_access_token

    client.post("/api/v1/kbs", json={"name": "mine"})
    other = {"Authorization": f"Bearer {create_access_token(str(UUID(int=99)))}"}

    assert client.get("/api/v1/kbs/stats/count").json() == {"count": 1}
    assert client.get("/api/v1/kbs/stats/count", headers=other).json() == {"count": 0}
