from __future__ import annotations

from uuid import UUID

from fastapi import Header

from kb_service.core.exceptions import UnauthorizedError
from kb_service.core.security import decode_access_token


async def get_current_user_id(authorization: str | None = Header(default=None)) -> UUID:
    """从 `Authorization: Bearer <token>` 解析当前用户。

    W8 TODO：换成 OAuth2PasswordBearer + 用户表校验（校验用户是否存在/是否被封禁）。
    """
    if not authorization:
        raise UnauthorizedError("缺少认证信息")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise UnauthorizedError("认证头格式应为 Bearer <token>")
    payload = decode_access_token(token)
    sub = payload.get("sub")
    if not sub:
        raise UnauthorizedError("凭证缺少 subject")
    return UUID(str(sub))
