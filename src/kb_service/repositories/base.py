from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4


class InMemoryStore:
    """极简内存存储（W1-W6 使用）。

    目的：在没有数据库的情况下先把"分层"跑通，让 api/service 层
    与持久化实现解耦。W7 起把它换成 SQLAlchemy Repository，service 层代码基本不动。
    """

    def __init__(self) -> None:
        self.kbs: dict[UUID, dict[str, Any]] = {}
        self.docs: dict[UUID, dict[str, Any]] = {}

    def new_id(self) -> UUID:
        return uuid4()

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)


store = InMemoryStore()
