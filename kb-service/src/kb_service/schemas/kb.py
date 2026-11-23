from __future__ import annotations

from datetime import datetime
from typing import Annotated, Generic, Self, TypeVar
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

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

    @model_validator(mode="after")
    def _reject_explicit_null_name(self) -> Self:
        """`{"name": null}` 是 422，不是 200 原值不变、也不是 500。

        判据：`model_fields_set` 记录"客户端到底传了哪些键"，
        所以"没传 name"（合法，部分更新）和"传了 name 但值为 null"（非法，名称必须有值）
        能区分开——只靠 `is None` 分不出来，这正是债②的根因。
        """
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name 不能置空：改名就传新名字，不改就别传这个字段")
        return self


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
