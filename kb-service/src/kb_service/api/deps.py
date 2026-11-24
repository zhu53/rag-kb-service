from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from kb_service.core.db import get_db
from kb_service.core.exceptions import ForbiddenError, UnauthorizedError
from kb_service.core.security import decode_access_token
from kb_service.repositories.rows import UserRow
from kb_service.repositories.user_repo import UserRepository

# HTTPBearer 让 OpenAPI 文档自动生成 Authorize 按钮（右上角 🔓），
# 在 /docs 里填 token 后，所有接口会自动带上 Authorization 头。
# scheme_name 会显示在 Authorize 弹窗里。
_bearer_scheme = HTTPBearer(
    scheme_name="Bearer Token",
    description="粘贴登录返回的 access_token（不要自己加 Bearer 前缀）",
    # auto_error=False：头缺失时不由框架抛 403，而是进入函数体由我们抛统一的业务异常
    auto_error=False,
)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: Session = Depends(get_db),
) -> UserRow:
    if credentials is None:
        raise UnauthorizedError("缺少认证信息")
    claims = decode_access_token(credentials.credentials)
    try:
        user_id = UUID(claims.sub)
    except ValueError as exc:
        raise UnauthorizedError("凭证 subject 不是合法用户") from exc

    row = UserRepository(session).get(user_id)
    if row is None:
        raise UnauthorizedError("用户不存在")
    if row["is_banned"]:
        raise UnauthorizedError("账号已被封禁")
    return row


def require_role(*roles: str) -> Callable[..., Awaitable[UserRow]]:
    """依赖工厂：返回一个 FastAPI 依赖函数 (闭包记住要求的角色)。

    返回类型写 `Callable[..., Awaitable[UserRow]]` 而不是 `Callable[[], ...]`：
    内层参数的默认值是 `Depends(...)`，FastAPI 会自己注入，调用方"可以不传"，
    所以参数列表是"任意（此处恰好 0 个）"。
    """

    async def _check(user: UserRow = Depends(get_current_user)) -> UserRow:
        if user["role"] not in roles:
            raise ForbiddenError("权限不足")
        return user

    return _check
