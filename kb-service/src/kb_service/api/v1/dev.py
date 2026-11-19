"""仅开发环境挂载的演示端点（见 main.py 的条件 include）。

为什么存在：页面需要一个 token 才能过 `get_current_user_id`，而正式的
登录端点（用户表 + 密码校验）在 W8 才接。这个端点只做"签发"，不做
"认证"——谁都能拿 token，所以它必须永远不进 prod。

W8 TODO：登录端点上线后删除本文件（连同 main.py 里的挂载）。
"""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter
from pydantic import BaseModel

from kb_service.core.security import create_access_token

router = APIRouter(prefix="/dev")


class DevTokenRequest(BaseModel):
    """user_id 不传就现场生成一个——演示时等于"随机新用户"。"""

    user_id: UUID | None = None


class DevTokenResponse(BaseModel):
    access_token: str
    user_id: UUID


@router.post("/token", summary="[dev] 签发演示 token", response_model=DevTokenResponse)
async def issue_dev_token(body: DevTokenRequest) -> DevTokenResponse:
    uid = body.user_id or uuid4()
    return DevTokenResponse(access_token=create_access_token(str(uid)), user_id=uid)
