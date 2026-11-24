from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from kb_service.core.db import get_db
from kb_service.core.security import create_access_token
from kb_service.main import create_app
from kb_service.repositories.models import Base, User

TEST_USER_ID = UUID("11111111-1111-4111-8111-111111111111")


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    """整个测试会话共用一个 sqlite 内存库。

    `StaticPool` 是必须的：默认连接池下每个连接都是一个独立的 `:memory:` 库，
    session A 建的表 session B 看不见。StaticPool 复用同一个连接，才有一个共享库。

    这里用 `create_all` 修表结构是**合法**的，和 W7-D5 里被否决的那种用法不同：
    测试要的是"从零直接到最新结构"，没有存量数据、不需要演进、不需要回退；
    而生产要的是"从当前版本走到下一版"，那才必须交给 Alembic。
    判据：**有没有历史状态要维护**。测试没有，生产有。
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def db(app: FastAPI, db_engine: Engine) -> Iterator[Session]:
    """每个测试：清表 → 开 session → 把 get_db 换成它。

    autouse 的理由：只要漏掉一个测试，它就会拿着真 `get_db` 去打 dev 库，
    往 kb_dev 写脏数据、还和别的用例串数据（今天就是这么红的：assert 2 == 1）。
    测试的隔离不能靠"记得加装饰器"。
    """
    with db_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())

    session = sessionmaker(bind=db_engine, expire_on_commit=False)()

    # D3 起鉴权走真链路：get_current_user 拿 token 里的 sub 查库验人。
    # auth_headers 的 token 指向 TEST_USER_ID，库里必须真有这个人，
    # 否则所有带凭证的请求都会 401「用户不存在」。
    # password_hash 是占位串——测试里没人验证密码，登录走的是 auth_service 不走这里。
    session.add(
        User(
            id=TEST_USER_ID,
            email="seed@example.com",
            password_hash="x" * 60,
            role="member",
        )
    )
    session.flush()

    # 必须写成生成器函数：FastAPI 靠 inspect.isgeneratorfunction 判定
    # "这是 yield 型依赖，请求结束后要执行它 finally 之后的部分"。
    # 写成 lambda: iter([session]) 会被当成普通依赖，注入进去的是个迭代器。
    def _override_get_db() -> Iterator[Session]:
        yield session

    # 测试内的"请求"共用同一个 session：一次测试就是一个事务上下文，
    # 用例结束时整体回滚/清表，天然隔离；也省去每请求建连接的噪音。
    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.rollback()
        session.close()


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(TEST_USER_ID))}"}


@pytest.fixture(scope="session")
def app() -> FastAPI:
    return create_app()


@pytest.fixture
def client(app: FastAPI, auth_headers: dict[str, str]) -> Iterator[TestClient]:
    with TestClient(app, headers=auth_headers) as c:
        yield c
