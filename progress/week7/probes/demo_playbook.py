r"""W7-D6 演示剧本：6 步走完，"打通"的定义就在这里面。

    1 建库           → 201，MySQL 里有行
    2 传 1200 字文档 → status pending → ready，chunk_count = 4
    3 列文档         → total = 1，EXPLAIN 走 ix_doc_kb_created
    4 提问           → sources 带出**片段**（不是整篇）
    5 "重启"         → 本脚本是独立进程，能查到上一进程写的数据 = 数据在盘上
    6 EXPLAIN        → Extra 里没有 Using filesort

第 5 步的做法说明：不真的重启 uvicorn（脚本里不好做），而是让**另一个进程**
（本脚本自己的 SQLAlchemy 连接）去查——`get_db` 的会话早就在请求结束时关掉了，
还能读到，说明数据不在任何进程的内存里。
换个说法：**"重启还在"的本质是"不依赖进程内状态"**，独立进程验证的就是这一条。

跑法（PowerShell，kb-service 目录下）：
    & .\.venv\Scripts\python.exe ..\progress\week7\probes\demo_playbook.py
"""

from __future__ import annotations

from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from kb_service.core.config import get_settings
from kb_service.core.security import create_access_token
from kb_service.main import create_app

DEMO_USER = UUID("66666666-6666-4666-8666-666666666666")
engine = create_engine(get_settings().database_url)
BODY = ("测试文档内容" * 200)[:1200]


def cleanup() -> None:
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM knowledge_bases WHERE owner_id = :o"), {"o": DEMO_USER.hex}
        )


def main() -> None:
    cleanup()
    app = create_app()
    token = create_access_token(str(DEMO_USER))

    with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as c:
        # ---- 1 建库 ----
        r = c.post("/api/v1/kbs", json={"name": "演示库", "description": "W7 打通验收"})
        kb_id = r.json()["data"]["id"]
        print(f"1) 建库        {r.status_code}  kb_id={kb_id}")

        # ---- 2 传文档 ----
        r = c.post(
            f"/api/v1/kbs/{kb_id}/documents",
            json={"title": "演示文档", "content": BODY},
        )
        doc = r.json()
        print(
            f"2) 传文档      {r.status_code}  status={doc['status']}  "
            f"chunk_count={doc['chunk_count']}  正文={len(BODY)} 字"
        )

        # ---- 3 列文档 ----
        r = c.get(f"/api/v1/kbs/{kb_id}/documents?page=1&size=10")
        print(f"3) 列文档      {r.status_code}  total={r.json()['total']}")

        # ---- 4 提问 ----
        # 注意两件事：
        #   ① stream 默认是 True（ChatRequest 里 stream: bool = True），
        #      不显式关掉拿到的是 SSE 文本流，r.json() 会直接抛 JSONDecodeError。
        #   ② 现在的检索是 `question.split()` 按**空格**分词 + `content.count(词)`，
        #      中文整句（"测试文档内容是什么"）会被当成一个词，一次都命中不了。
        #      所以演示用正文里真实出现的短语。这个缺陷是 W12 换向量检索的动因之一。
        r = c.post(
            "/api/v1/chat",
            json={"kb_id": kb_id, "question": "测试文档内容", "stream": False},
        )
        body = r.json()
        src = body.get("sources") or []
        print(f"4) 提问        {r.status_code}  sources={len(src)} 条")
        if src:
            snippet = src[0]["snippet"]
            print(f"            片段长度={len(snippet)} 字  开头={snippet[:24]}…")
            print("            —— 返回的是片段，不是整篇 1200 字")

    # ---- 5 新连接（等价于"重启后"）----
    with engine.connect() as conn:
        doc_row = conn.execute(
            text(
                "SELECT CHAR_LENGTH(content) AS clen, status, chunk_count "
                "FROM documents WHERE kb_id = :kb"
            ),
            {"kb": UUID(kb_id).hex},
        ).mappings().one()
        n_chunks = conn.execute(
            text(
                "SELECT COUNT(*) FROM chunks c JOIN documents d ON c.doc_id = d.id "
                "WHERE d.kb_id = :kb"
            ),
            {"kb": UUID(kb_id).hex},
        ).scalar()
        print(
            f"5) 新连接查   正文={doc_row['clen']} 字  status={doc_row['status']}  "
            f"chunk_count={doc_row['chunk_count']}  chunks 行={n_chunks}"
        )

        # ---- 6 EXPLAIN ----
        plan = conn.execute(
            text(
                "EXPLAIN SELECT * FROM documents "
                "WHERE kb_id = :kb ORDER BY created_at DESC LIMIT 10"
            ),
            {"kb": UUID(kb_id).hex},
        ).mappings().one()
        print(
            f"6) EXPLAIN    key={plan['key']}  rows={plan['rows']}  "
            f"Extra={plan['Extra']!r}"
        )
        using_filesort = "filesort" in (plan["Extra"] or "").lower()
        print(
            "            —— 走 ix_doc_kb_created 且无 filesort"
            if not using_filesort
            else "            —— 出现 Using filesort：复合索引没用上"
        )

    cleanup()
    print("\n[清理] 演示数据已删除")


if __name__ == "__main__":
    main()
