"""W7-D5 收口自查：数据库到底接进业务链路了没有。

三段，每段只回答一个是/否：

A. HTTP 链路（TestClient 打真 app）——POST 建库拿到 201 之后，MySQL 里有行吗？
B. 手动把 session 传给 repo、只 flush 不 commit——另一个连接看得见吗？
C. 同一路径补一次 commit——看得见吗（顺带清理探针数据）。

跑法（PowerShell）：
    cd kb-service
    & .\.venv\Scripts\python.exe ..\progress\week7\probes\check_db_wiring.py
"""

from __future__ import annotations

from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from kb_service.core.config import get_settings
from kb_service.core.db import SessionLocal
from kb_service.core.security import create_access_token
from kb_service.main import create_app
from kb_service.repositories.kb_repo import KBRepository
from kb_service.schemas.kb import KBCreate

PROBE_USER = UUID("99999999-9999-4999-8999-999999999999")
engine = create_engine(get_settings().database_url)


def db_count() -> int:
    """用独立连接数行数——独立连接 = 别的会话，看不见未提交的东西。"""
    with engine.connect() as conn:
        value = conn.execute(text("SELECT COUNT(*) FROM knowledge_bases")).scalar()
        return int(value or 0)


def segment_a() -> None:
    print("\n[A] HTTP 链路：POST /api/v1/kbs")
    app = create_app()
    token = create_access_token(str(PROBE_USER))
    before = db_count()
    with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as client:
        resp = client.post(
            "/api/v1/kbs",
            json={"name": "探针A-HTTP建库", "description": "检查有没有落库"},
        )
        print(f"    POST 状态码 = {resp.status_code}")
        print(f"    返回体 data.id = {resp.json().get('data', {}).get('id')}")
        page = client.get("/api/v1/kbs")
        print(f"    紧接着 GET 列表 total = {page.json().get('total')}，此刻 MySQL 行数 = {db_count()}")
        print("      —— 两者相等 = 读的也是库（内存 store 已在 D6 删除，无处可逃）")
    after = db_count()
    verdict = "落库了" if after > before else "一行都没落"
    print(f"    MySQL 行数 {before} -> {after}：{verdict}")


def segment_b() -> None:
    print("\n[B] 传 session 给 repo，只 flush 不 commit")
    before = db_count()
    session: Session = SessionLocal()
    try:
        row = KBRepository(session).create(PROBE_USER, KBCreate(name="探针B-只flush"))
        print(f"    flush 后拿到主键 = {row['id']}（本会话可见）")
        print(f"    此时另一个连接看到 {db_count()} 行")
    finally:
        session.close()  # 未 commit 直接 close = ROLLBACK
    after = db_count()
    if after > before:
        verdict = "落库了"
    else:
        verdict = f"B 这一行回滚了（基线 {before} 行仍在，未被波及）"
    print(f"    close 之后 MySQL 行数 {before} -> {after}：{verdict}")


def segment_c() -> None:
    print("\n[C] 同一路径，补一次 commit")
    before = db_count()
    session: Session = SessionLocal()
    try:
        KBRepository(session).create(PROBE_USER, KBCreate(name="探针C-提交"))
        session.commit()
    finally:
        session.close()
    after = db_count()
    print(f"    commit 之后 MySQL 行数 {before} -> {after}：{'落库了' if after > before else '仍未落库'}")

    # 清理：只删本次探针写入的行
    with engine.begin() as conn:
        deleted = conn.execute(
            text("DELETE FROM knowledge_bases WHERE owner_id = :owner"),
            {"owner": PROBE_USER.hex},
        ).rowcount
    print(f"    清理掉 {deleted} 行探针数据，现在 {db_count()} 行")


def main() -> None:
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
        tables = conn.execute(text("SHOW TABLES")).scalars().all()
    print(f"[环境] {get_settings().database_url}")
    print(f"[环境] alembic 版本 = {version}，表 = {tables}")

    segment_a()
    segment_b()
    segment_c()
    print("\n[结论] A 段决定「接口有没有连库」，B/C 段决定「连了之后数据留不留得住」。")


if __name__ == "__main__":
    main()
