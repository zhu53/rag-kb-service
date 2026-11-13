"""D1：Session / 事务语义的最小验证集。

四个测试对应教材 §零 时间轴上的四个刻度：
1. commit 才落库
2. close 未提交 = 回滚
3. SessionLocal 不是单例（一次请求一个，靠依赖缓存复用）
4. repo.create 只 flush 不 commit（主键拿到了，别人还看不见）

最后两个补测 get_db 这个「yield 依赖」的两条出口（正常收尾 / 异常回滚）。
"""

from collections.abc import Generator, Iterator
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from kb_service.core import db as db_module
from kb_service.core.db import get_db
from kb_service.repositories.kb_repo import KBRepository
from kb_service.repositories.models import Base, KnowledgeBase
from kb_service.schemas.kb import KBCreate


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    """每个测试一个独立的临时库文件。

    不用 sqlite:///:memory: —— 内存库以「连接」为单位，create_all 用的连接和
    后面查询用的连接是两个不同的内存库，表根本不存在（除非配 StaticPool）。
    """
    eng = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


def _count(engine: Engine) -> int:
    """另开一个 Session 数行数 —— 用新会话才看得到「别人提交了没有」。"""
    with Session(engine) as s:
        return s.scalar(select(func.count()).select_from(KnowledgeBase)) or 0


def test_commit_persists(engine: Engine) -> None:
    with Session(engine) as s1:
        s1.add(KnowledgeBase(name="会提交", owner_id=uuid4()))
        s1.commit()

    assert _count(engine) == 1


def test_close_without_commit_rolls_back(engine: Engine) -> None:
    with Session(engine) as s1:
        s1.add(KnowledgeBase(name="不提交", owner_id=uuid4()))
        s1.flush()  # INSERT 已经发出去了
        # 不 commit，退出 with 触发 close()

    # close 对未提交事务等价于 ROLLBACK
    assert _count(engine) == 0


def test_session_not_singleton(engine: Engine) -> None:
    """一次请求一个 session，靠依赖缓存保证同一请求内复用 —— 不是全局单例。"""
    factory = sessionmaker(bind=engine)

    a = factory()
    b = factory()
    try:
        assert a is not b
    finally:
        a.close()
        b.close()


def test_repo_create_flushes_but_does_not_commit(engine: Engine) -> None:
    """repo.create 只 flush：拿得到主键，但别的会话看不见 —— 提交权在 service 层。"""
    owner_id = uuid4()

    with Session(engine) as s1:
        row = KBRepository(s1).create(owner_id, KBCreate(name="只 flush"))

        # flush 后主键已生成，DTO 能正常返回
        assert row["id"] is not None
        assert row["name"] == "只 flush"
        assert row["doc_count"] == 0

        # 事务还没提交：别的会话看不到这一行
        assert _count(engine) == 0

        # 提交之后才可见
        s1.commit()

    assert _count(engine) == 1


def test_get_db_closes_session_on_normal_exit(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """正常走完（响应已生成）→ 生成器收尾执行 close。"""
    calls: list[str] = []

    class RecordingSession(Session):
        def close(self) -> None:
            calls.append("close")
            super().close()

    monkeypatch.setattr(
        db_module, "SessionLocal", sessionmaker(bind=engine, class_=RecordingSession)
    )

    gen = get_db()
    assert isinstance(next(gen), Session)
    with pytest.raises(StopIteration):
        next(gen)

    assert calls == ["close"]  # 没有 commit，也没有 rollback


def test_get_db_rolls_back_then_closes_on_error(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """handler 抛异常 → 依赖里先 rollback 再 close，并且异常原样抛出（不能吞）。"""
    calls: list[str] = []

    class RecordingSession(Session):
        def rollback(self) -> None:
            calls.append("rollback")
            super().rollback()

        def close(self) -> None:
            calls.append("close")
            super().close()

    monkeypatch.setattr(
        db_module, "SessionLocal", sessionmaker(bind=engine, class_=RecordingSession)
    )

    gen = cast("Generator[Session, None, None]", get_db())
    next(gen)
    with pytest.raises(RuntimeError, match="boom"):
        gen.throw(RuntimeError("boom"))

    assert calls == ["rollback", "close"]
