"""UserRepository / UserRow 契约测试（D1 清债：补覆盖率）。

验证三件事：
① create + get_by_email 走通；② 快照 UserRow **不含 password_hash**（敏感列不外带）；
③ get 主键查 + 未命中返回 None。
用 conftest 的 sqlite 内存库，不碰真库（2026-11-19 CI #43 教训）。
"""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from kb_service.repositories.models import User
from kb_service.repositories.user_repo import UserRepository


@pytest.fixture
def session(db_engine: Engine) -> Iterator[Session]:
    """独立 session：每个测试自己 flush/commit，结束关闭。"""
    factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    s = factory()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def test_create_returns_snapshot_without_password_hash(session: Session) -> None:
    row = UserRepository(session).create(email="a@test.dev", password_hash="x" * 60)
    session.commit()

    assert row["email"] == "a@test.dev"
    assert row["role"] == "member"  # 模型 default 在 Python 侧生效
    assert row["is_banned"] is False
    # 敏感列绝不能出现在快照里
    assert "password_hash" not in row


def test_get_by_email_hits_and_misses(session: Session) -> None:
    repo = UserRepository(session)
    repo.create(email="b@test.dev", password_hash="x" * 60)
    session.commit()

    hit = repo.get_by_email("b@test.dev")
    assert hit is not None
    assert hit["email"] == "b@test.dev"
    assert repo.get_by_email("nobody@test.dev") is None


def test_get_by_primary_key(session: Session) -> None:
    uid = uuid4()
    session.add(User(id=uid, email="c@test.dev", password_hash="x" * 60))
    session.commit()

    row = UserRepository(session).get(uid)
    assert row is not None
    assert row["id"] == uid
    assert UserRepository(session).get(uuid4()) is None  # 未命中 → None，上层必须处理
