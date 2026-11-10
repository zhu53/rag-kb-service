from __future__ import annotations

from fastapi.testclient import TestClient


def test_kb_crud_flow(client: TestClient) -> None:
    # create
    r = client.post("/api/v1/kbs", json={"name": "考研资料", "description": "重邮复试"})
    assert r.status_code == 201, r.text
    kb = r.json()["data"]
    assert r.json()["code"] == 0
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
    assert r.json()["code"] == 40400


def test_create_kb_validation_error(client: TestClient) -> None:
    r = client.post("/api/v1/kbs", json={"name": ""})
    assert r.status_code == 422
    assert r.json()["code"] == 42200


def test_document_upload_and_chunk(client: TestClient) -> None:
    kb_id = client.post("/api/v1/kbs", json={"name": "kb"}).json()["data"]["id"]
    content = "人工智能" * 500

    r = client.post(
        f"/api/v1/kbs/{kb_id}/documents",
        json={"title": "note.md", "content": content},
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["status"] == "ready"
    assert doc["chunk_count"] > 1

    # 知识库的 doc_count 应当同步 +1（get_kb 响应已套 ApiResponse 壳）
    assert client.get(f"/api/v1/kbs/{kb_id}").json()["data"]["doc_count"] == 1


def test_chat_returns_sources(client: TestClient) -> None:
    kb_id = client.post("/api/v1/kbs", json={"name": "kb"}).json()["data"]["id"]
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
    kb_id = client.post("/api/v1/kbs", json={"name": "kb"}).json()["data"]["id"]
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


def test_list_kbs_default_pagination(client: TestClient) -> None:
    """不带 query 参数时走 PageParams 的默认值：page=1、size=20。"""
    for i in range(3):
        client.post("/api/v1/kbs", json={"name": f"kb-{i}"})

    r = client.get("/api/v1/kbs")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["size"] == 20


def test_list_kbs_size_over_limit(client: TestClient) -> None:
    """size 超上限由 PageParams 的 Field 拦住，错误走统一 422 壳。"""
    r = client.get("/api/v1/kbs?size=500")

    assert r.status_code == 422
    body = r.json()
    assert body["code"] == 42200
    assert body["message"] == "参数校验失败"
    assert "size" in str(body["data"])


def test_list_docs_shares_page_params(client: TestClient) -> None:
    """文档列表复用同一个 PageParams：同一个依赖在两处生效。"""
    kb_id = client.post("/api/v1/kbs", json={"name": "kb"}).json()["data"]["id"]

    ok = client.get(f"/api/v1/kbs/{kb_id}/documents")
    assert ok.status_code == 200
    assert ok.json()["page"] == 1
    assert ok.json()["size"] == 20

    bad = client.get(f"/api/v1/kbs/{kb_id}/documents?size=500")
    assert bad.status_code == 422
    assert bad.json()["code"] == 42200
