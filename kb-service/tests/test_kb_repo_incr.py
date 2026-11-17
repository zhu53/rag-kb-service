"""交付物 4：incr_doc_count 原子自增的三个验收测试。

对应教材 §12 交付物 4：
1. 单次调用恰好发出 1 条 SQL（before_cursor_execute 计数）——读-改-写是 2 条，这里是 1 条
2. 同一 session 顺序自增 20 次，最终 doc_count == 20
   （真并发下的原子性验证留 MySQL 集成测试：SQLite 文件库多线程会锁库，测不了）
3. kb 不存在 → NotFoundError（靠 rowcount == 0 判断，不发额外 SELECT）
"""

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from kb_service.core.exceptions import NotFoundError
from kb_service.repositories.kb_repo import KBRepository
from kb_service.repositories.models import Base, KnowledgeBase
from kb_service.schemas.kb import KBCreate


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def sql_log(engine: Engine) -> Iterator[list[str]]:
    """记录这个 engine 上真实执行过的每条 SQL。"""
    statements: list[str] = []

    def _rec(_conn: object, _cursor: object, statement: str, *_args: object) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _rec)
    yield statements
    event.remove(engine, "before_cursor_execute", _rec)


def test_incr_issues_single_sql(engine: Engine, sql_log: list[str]) -> None:
    """原子自增 = 1 条 UPDATE；如果实现里混进了 SELECT，这条就红。"""
    with Session(engine) as session:
        row = KBRepository(session).create(uuid4(), KBCreate(name="计数"))
        session.commit()

        sql_log.clear()
        KBRepository(session).incr_doc_count(row["id"], 1)

        assert len(sql_log) == 1
        assert sql_log[0].startswith("UPDATE")


def test_twenty_sequential_increments_reach_twenty(engine: Engine) -> None:
    """语义验证：20 次自增后恰好是 20（真并发验证留 MySQL 集成测试）。"""
    with Session(engine) as session:
        repo = KBRepository(session)
        row = repo.create(uuid4(), KBCreate(name="自增20"))
        session.commit()

        for _ in range(20):
            repo.incr_doc_count(row["id"], 1)
        session.commit()

        final = session.scalar(select(KnowledgeBase.doc_count).where(KnowledgeBase.id == row["id"]))
        assert final == 20


def test_missing_kb_raises_not_found(engine: Engine) -> None:
    with Session(engine) as session, pytest.raises(NotFoundError):
        KBRepository(session).incr_doc_count(uuid4(), 1)
