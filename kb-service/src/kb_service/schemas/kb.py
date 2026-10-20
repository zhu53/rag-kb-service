from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class KBBase(BaseModel):
    name: str = Field(min_length=1, max_length=100, description="知识库名称")
    description: str | None = Field(default=None, max_length=500)


class KBCreate(KBBase):
    pass


class KBUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)


class KBOut(KBBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    doc_count: int = 0
    created_at: datetime
    updated_at: datetime


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """通用分页响应。

    注意：这里用 `Generic[T]` 而不是 PEP 695 的 `class Page[T](...)` ——
    后者是 Python 3.12+ 语法，本项目锁定 3.11。这是真实项目里常见的
    兼容性考量：语法糖晚于类型系统本身。
    """

    items: list[T]
    total: int
    page: int
    size: int
