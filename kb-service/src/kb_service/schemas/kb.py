from __future__ import annotations

from datetime import datetime
from typing import Annotated, Generic, TypeVar
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from kb_service.schemas.common import not_blank

# 约束 + 校验器一起抽成类型别名：KBBase / KBCreate / KBUpdate 三处复用，改一处全部生效。
KbName = Annotated[
    str,
    Field(min_length=1, max_length=100, description="知识库名称"),
    AfterValidator(not_blank),
]
KbDescription = Annotated[str | None, Field(default=None, max_length=500)]


class KBBase(BaseModel):
    name: KbName
    description: KbDescription = None


class KBCreate(KBBase):
    # 入参契约收紧：多传字段直接 422（extra_forbidden），不再静默丢弃。
    # alias 让客户端可以传 kbName；populate_by_name 让字段名 name 也被接受——两条路都能构造。
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    name: KbName = Field(alias="kbName")


class KBUpdate(BaseModel):
    # 不继承 KBBase（全字段可选语义不同），但复用同一组别名——PATCH 路径约束不漏。
    name: KbName | None = None
    description: KbDescription = None


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
