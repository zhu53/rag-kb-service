from __future__ import annotations

from enum import StrEnum
from typing import Any


class AppError(Exception):
    """业务异常基类：所有可预期的业务错误都从这里派生子类。

    好处：service 层只管 raise，不用关心 HTTP 状态码；由 API 层的
    异常处理器统一翻译成响应体，业务代码与 Web 框架解耦。
    """

    code: str = "APP_ERROR"
    http_status: int = 400
    message: str = "请求处理失败"

    def __init__(self, message: str | None = None, *, detail: Any = None) -> None:
        self.message = message or self.message
        self.detail = detail
        super().__init__(self.message)


class NotFoundError(AppError):
    code = "NOT_FOUND"
    http_status = 404
    message = "资源不存在"


class ConflictError(AppError):
    code = "CONFLICT"
    http_status = 409
    message = "资源冲突"


class UnauthorizedError(AppError):
    code = "UNAUTHORIZED"
    http_status = 401
    message = "未认证或凭证已过期"


class ForbiddenError(AppError):
    code = "FORBIDDEN"
    http_status = 403
    message = "无权限访问该资源"


class RateLimitError(AppError):
    code = "RATE_LIMITED"
    http_status = 429
    message = "请求过于频繁，请稍后再试"


class BadRequestError(AppError):
    code = "BAD_REQUEST"
    http_status = 400
    message = "请求参数有误"


class ErrorCode(StrEnum):
    """前端可依赖的错误码枚举（对外契约的一部分）。"""

    APP_ERROR = "APP_ERROR"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMITED = "RATE_LIMITED"
    BAD_REQUEST = "BAD_REQUEST"
