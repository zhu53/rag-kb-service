from __future__ import annotations

from datetime import datetime
from typing import TypedDict
from uuid import UUID


class KBRow(TypedDict):
    """kb_service.store 里一行知识库的结构。"""

    id: UUID
    owner_id: UUID
    name: str
    description: str | None
    doc_count: int
    created_at: datetime
    updated_at: datetime


class DocRow(TypedDict):
    """doc_service.store 里一行文档的结构。"""

    id: UUID
    kb_id: UUID
    title: str
    content: str
    status: str
    chunk_count: int
    created_at: datetime
    updated_at: datetime


class UserRow(TypedDict):
    """users 表的对外快照。

    两个字段刻意**不在**快照里：
    - `password_hash`：敏感列，名字防明文塞进去（repo.create 参数名），
      快照防明文带出来（返回体）——同一件事的两端。
    - `updated_at`：快照最小化，D4 的 get_current_user 用不到就不带；
      真要展示"最近改过"时再加，加字段的改动是局部的。
    """

    id: UUID
    email: str
    role: str
    is_banned: bool
    created_at: datetime


class UserCredentialsRow(TypedDict):
    """
    登录必须要password_hash
    只返回 id + hash，最小暴露
    """

    id: UUID
    password_hash: str
    is_banned: bool
