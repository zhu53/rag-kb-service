from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


def not_blank(v: str) -> str:
    """strip 后为空则拒绝；非空则返回 strip 后的值。"""
    stripped = v.strip()
    if not stripped:
        raise ValueError("不能全是空白字符")
    return stripped


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "ok"
    data: T | None = None
