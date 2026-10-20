from __future__ import annotations

from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from kb_service.core.exceptions import UnauthorizedError
from kb_service.core.security import decode_access_token

# HTTPBearer 让 OpenAPI 文档自动生成 Authorize 按钮（右上角 🔓），
# 在 /docs 里填 token 后，所有接口会自动带上 Authorization 头。
# scheme_name 会显示在 Authorize 弹窗里。
_bearer_scheme = HTTPBearer(
    scheme_name="Bearer Token",
    description="粘贴登录返回的 access_token（不要自己加 Bearer 前缀）",
    # auto_error=False：头缺失时不由框架抛 403，而是进入函数体由我们抛统一的业务异常
    auto_error=False,
)


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> UUID:
    """从 `Authorization: Bearer <token>` 解析当前用户。

    依赖 HTTPBearer 安全方案：
    - /docs 右上角出现 Authorize 按钮（这就是你之前找不到它的原因）
    - 头缺失/格式错时返回 None，由这里抛业务异常（保证错误响应格式统一）
    - 校验通过后返回 credentials.credentials（即纯 token 字符串）

    W8 TODO：换成 OAuth2PasswordBearer + 用户表校验（校验用户是否存在/是否被封禁）。
    """
    if credentials is None:
        raise UnauthorizedError("缺少认证信息")
    # HTTPBearer 已校验 scheme 必须是 Bearer，这里只需处理 token 本身
    payload = decode_access_token(credentials.credentials)
    sub = payload.get("sub")
    if not sub:
        raise UnauthorizedError("凭证缺少 subject")
    return UUID(str(sub))
