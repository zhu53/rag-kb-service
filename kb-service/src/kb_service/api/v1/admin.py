"""admin 专属接口：只有 role=admin 能进。

权限逐路由声明 `Depends(require_role("admin"))`：也可以在 `router.py` 里整挂
`dependencies=[...]`，但逐路由声明能把 admin 行拿到手（将来"不能封自己"要用），
两种写法语义等价，都靠依赖缓存让 get_current_user 只查一次库。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from kb_service.api.deps import require_role
from kb_service.core.db import get_db
from kb_service.core.exceptions import NotFoundError
from kb_service.repositories.rows import UserRow
from kb_service.repositories.user_repo import UserRepository
from kb_service.schemas.auth import UserAdminOut
from kb_service.schemas.common import ApiResponse

router = APIRouter()


@router.get("/users", summary="列出全部用户（admin）")
async def list_users(
    _admin: UserRow = Depends(require_role("admin")),
    session: Session = Depends(get_db),
) -> ApiResponse[list[UserAdminOut]]:
    rows = UserRepository(session).get_all_users()
    return ApiResponse[list[UserAdminOut]](data=[UserAdminOut.model_validate(row) for row in rows])


@router.patch("/users/{user_id}/ban", summary="封禁用户（admin）")
async def ban_user(
    user_id: UUID,
    _admin: UserRow = Depends(require_role("admin")),
    session: Session = Depends(get_db),
) -> ApiResponse[UserAdminOut]:
    # 这条链没有业务规则（改一个布尔位），不单开 service 层，commit 留在路由；
    # 一旦有"不能封自己""写审计日志"这类规则，就该抽 service 了。
    row = UserRepository(session).set_banned(user_id, True)
    if row is None:
        raise NotFoundError("用户不存在")
    session.commit()
    return ApiResponse[UserAdminOut](data=row)
