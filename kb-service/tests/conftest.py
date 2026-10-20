from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from kb_service.core.security import create_access_token
from kb_service.main import create_app
from kb_service.repositories.base import store

TEST_USER_ID = UUID("11111111-1111-4111-8111-111111111111")


@pytest.fixture(autouse=True)
def _clear_store() -> Iterator[None]:
    """每个测试都从干净的内存存储开始，避免用例间相互污染。"""
    store.kbs.clear()
    store.docs.clear()
    yield
    store.kbs.clear()
    store.docs.clear()


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(TEST_USER_ID))}"}


@pytest.fixture
def client(auth_headers: dict[str, str]) -> Iterator[TestClient]:
    with TestClient(create_app(), headers=auth_headers) as c:
        yield c
