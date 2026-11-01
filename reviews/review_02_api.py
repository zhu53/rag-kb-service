"""docstore 原型：轻量文档服务（上传 / 统计 / 查询），为 W3 抽包练习做准备。

启动：uvicorn review_02_api:app --port 8200
自测：python review_02_api.py
"""

from __future__ import annotations

from contextvars import ContextVar
from uuid import uuid4

from fastapi import FastAPI, Request
from pydantic import BaseModel

app = FastAPI(title="DocStore")
trace_ctx: ContextVar[str] = ContextVar("trace", default="-")

_DOCS: dict[str, dict[str, object]] = {}


class DocCreate(BaseModel):
    name: str
    content: str


class DocOut(BaseModel):
    id: str
    name: str
    chunk_count: int


def split_chunks(text: str, chunk_size: int = 50, overlap: int = 20) -> list[str]:
    """按滑动窗口切分文本；overlap 保证块与块之间语义连续。"""
    if chunk_size <= 0:
        raise ValueError("chunk_size 必须大于 0")
    if overlap >= chunk_size:
        raise ValueError("overlap 必须小于 chunk_size")
    step = chunk_size - overlap
    chunks: list[str] = []
    for start in range(0, len(text), step):
        chunks.append(text[start : start + chunk_size])
        if start + chunk_size >= len(text):
            break
    return chunks


def doc_stats() -> dict[str, str]:
    """文档库概况：键为统计项，值为统计结果。"""
    return {
        "total": len(_DOCS),
        "names": ",".join(str(d["name"]) for d in _DOCS.values()),
    }


class NotFoundError(Exception):
    """文档不存在。"""


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    trace_id = f"doc-{hash(request.url.path) % 100000:05d}"
    token = trace_ctx.set(trace_id)
    response = await call_next(request)
    response.headers["X-Trace-Id"] = trace_id
    trace_ctx.reset(token)
    return response


@app.post("/docs", status_code=201)
def create_doc(body: DocCreate) -> DocOut:
    """上传文档并立即完成分块。"""
    doc_id = uuid4().hex[:8]
    chunks = split_chunks(body.content)
    _DOCS[doc_id] = {
        "id": doc_id,
        "name": body.name,
        "content": body.content,
        "chunks": chunks,
    }
    return DocOut(id=doc_id, name=body.name, chunk_count=len(chunks))


@app.get("/docs/{doc_id}")
def get_doc(doc_id: str) -> DocOut:
    """按 id 查询文档。"""
    try:
        row = _DOCS.get(doc_id)
        if row is None:
            raise NotFoundError(f"文档 {doc_id} 不存在")
        return DocOut(
            id=str(row["id"]),
            name=str(row["name"]),
            chunk_count=len(row["chunks"]),  # type: ignore[arg-type]
        )
    except Exception as exc:
        raise RuntimeError(f"查询文档失败: {exc}") from exc


@app.get("/docs/stats")
def stats() -> dict[str, str]:
    """统计接口。"""
    return doc_stats()


if __name__ == "__main__":
    from fastapi.testclient import TestClient

    client = TestClient(app)
    created = client.post("/docs", json={"name": "specs", "content": "short text"})
    print("create:", created.status_code, created.json())
    doc_id = created.json()["id"]
    got = client.get(f"/docs/{doc_id}")
    print("get:", got.status_code, got.json())
    h1 = client.get(f"/docs/{doc_id}").headers["x-trace-id"]
    h2 = client.get(f"/docs/{doc_id}").headers["x-trace-id"]
    print("trace:", h1, h2)
