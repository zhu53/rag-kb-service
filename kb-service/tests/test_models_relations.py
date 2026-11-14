"""D2：关系 / 级联 / 外键 / N+1 四条回归。"""

from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kb_service.repositories.doc_repo import DocRepository
from kb_service.repositories.models import Base, Document, KnowledgeBase
from kb_service.schemas.doc import DocCreate


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = create_engine(f"sqlite:///{tmp_path / 't.db'}")

    @event.listens_for(eng, "connect")
    def _fk_on(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


def _new_kb(s: Session) -> UUID:
    kb = KnowledgeBase(name="kb", owner_id=uuid4())
    s.add(kb)
    s.flush()
    return kb.id  # ← 必须在 session 活着时取，见坑②


def test_create_doc_shows_up_in_kb_docs(engine: Engine) -> None:
    with Session(engine) as s:
        kb_id = _new_kb(s)
        DocRepository(s).create(kb_id, DocCreate(title="doc-a", content="正文"))
        s.commit()

    with Session(engine) as s2:
        kb = s2.get(KnowledgeBase, kb_id)
        assert kb is not None
        assert [d.title for d in kb.docs] == ["doc-a"]


def test_delete_kb_cascades_documents(engine: Engine) -> None:
    with Session(engine) as s:
        kb_id = _new_kb(s)
        repo = DocRepository(s)
        repo.create(kb_id, DocCreate(title="d1", content="正文"))
        repo.create(kb_id, DocCreate(title="d2", content="正文"))
        s.commit()

        s.delete(s.get(KnowledgeBase, kb_id))
        s.commit()

    with Session(engine) as s2:
        left = s2.scalars(select(Document).where(Document.kb_id == kb_id)).all()
        assert len(left) == 0


def test_fk_rejects_orphan_document(engine: Engine) -> None:
    with Session(engine) as s, pytest.raises(IntegrityError):
        DocRepository(s).create(uuid4(), DocCreate(title="orphan", content="正文"))


def test_list_by_kb_uses_two_sql(engine: Engine) -> None:
    with Session(engine) as s:
        kb_id = _new_kb(s)
        for i in range(3):
            DocRepository(s).create(kb_id, DocCreate(title=f"d{i}", content="正文"))
        s.commit()

    sqls: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _rec(conn, cursor, statement, parameters, context, executemany):
        sqls.append(statement)

    with Session(engine) as s2:
        rows, total = DocRepository(s2).list_by_kb(kb_id, offset=0, limit=2)

    assert len(sqls) == 2
    assert total == 3
    assert len(rows) == 2
