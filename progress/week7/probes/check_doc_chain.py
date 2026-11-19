"""W7-D6 步骤 3 验收：Doc 链路（文档正文 + chunks + 计数器）到底有没有落库。

一条命令回答四个问题：
  1. documents.content 里真有正文吗（不是空串/不是 0 长度）
  2. chunks 表里有几行，和 chunk_count 对得上吗
  3. documents.status 走到 ready 了吗
  4. knowledge_bases.doc_count 自增了吗

跑法（PowerShell，kb-service 目录下）：
    & .\.venv\Scripts\python.exe ..\progress\week7\probes\check_doc_chain.py

预期（1200 字正文，chunk_size=400 / overlap=50 → step=350 → 4 块）：
    正文长度 1200 / chunks 4 / chunk_count 4 / status ready / doc_count 1
"""

from __future__ import annotations

from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from kb_service.core.config import get_settings
from kb_service.core.security import create_access_token
from kb_service.main import create_app

PROBE_USER = UUID("88888888-8888-4888-8888-888888888888")
engine = create_engine(get_settings().database_url)

# 6 字 × 200 = 1200 字，长度可控，切块数可预先算出来
BODY = ("测试文档内容" * 200)[:1200]


def cleanup() -> None:
    """按 owner 清场，DB 的 FK CASCADE 会带走 documents / chunks。"""
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM knowledge_bases WHERE owner_id = :owner"),
            {"owner": PROBE_USER.hex},
        )


def main() -> None:
    cleanup()  # 基线归零，保证每次跑的读数干净

    app = create_app()
    token = create_access_token(str(PROBE_USER))
    with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as client:
        kb = client.post("/api/v1/kbs", json={"name": "探针-文档链"})
        print(f"[1] 建库 {kb.status_code}，kb_id = {kb.json().get('data', {}).get('id')}")
        kb_id = kb.json()["data"]["id"]

        doc = client.post(
            f"/api/v1/kbs/{kb_id}/documents",
            json={"title": "探针文档", "content": BODY},
        )
        print(f"[2] 传文档 {doc.status_code}，body 里 status = {doc.json().get('status')}，"
              f"chunk_count = {doc.json().get('chunk_count')}")
        print(f"    正文长度（请求里带的）= {len(BODY)}")

    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT CHAR_LENGTH(content) AS clen, status, chunk_count "
                "FROM documents WHERE kb_id = :kb"
            ),
            {"kb": UUID(kb_id).hex},
        ).mappings().one()
        chunks = conn.execute(
            text("SELECT COUNT(*) FROM chunks WHERE doc_id IN "
                 "(SELECT id FROM documents WHERE kb_id = :kb)"),
            {"kb": UUID(kb_id).hex},
        ).scalar()
        kb_row = conn.execute(
            text("SELECT doc_count FROM knowledge_bases WHERE id = :kb"),
            {"kb": UUID(kb_id).hex},
        ).scalar()

    print("\n===== 库里的事实 =====")
    print(f"    documents.content 长度 = {row['clen']}   （期望 1200）")
    print(f"    documents.status       = {row['status']}   （期望 ready）")
    print(f"    documents.chunk_count  = {row['chunk_count']}   （期望 4）")
    print(f"    chunks 表行数          = {chunks}   （期望 4）")
    print(f"    knowledge_bases.doc_count = {kb_row}   （期望 1）")

    verdict = (
        row["clen"] == 1200
        and row["status"] == "ready"
        and row["chunk_count"] == 4
        and chunks == 4
        and kb_row == 1
    )
    print(f"\n[结论] {'Doc 链路通了' if verdict else '有对不上的项，看上面哪行红'}")

    cleanup()
    print("[清理] 探针数据已删除")


if __name__ == "__main__":
    main()
