from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from kb_service.api.deps import get_current_user
from kb_service.core.db import get_db
from kb_service.repositories.kb_repo import KBRepository
from kb_service.repositories.rows import UserRow
from kb_service.schemas.common import ApiResponse, PageParams
from kb_service.schemas.kb import KBCreate, KBOut, KBUpdate, Page
from kb_service.services.kb_service import KBService

router = APIRouter()


@router.post(
    "",
    summary="创建知识库",
    description="创建一个新的知识库。\n\n- 名称不可重复\n- 描述可为空",
    response_description="创建成功，返回知识库本体",
    responses={401: {"model": ApiResponse, "description": "未认证（code=40100）"}},
    status_code=201,
)
async def create_kb(
    body: KBCreate, user: UserRow = Depends(get_current_user), session: Session = Depends(get_db)
) -> ApiResponse[KBOut]:
    kb = KBService(KBRepository(session), session=session).create(user["id"], body)
    return ApiResponse[KBOut](data=kb)


@router.get("", summary="分页查询我的知识库")
async def list_kbs(
    params: Annotated[PageParams, Depends()],
    user: UserRow = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Page[KBOut]:
    return KBService(KBRepository(session), session=session).list(
        user["id"], params.page, params.size
    )


@router.get("/stats/count", summary="我的知识库总数")
async def count_kbs(
    user: UserRow = Depends(get_current_user), session: Session = Depends(get_db)
) -> dict[str, int]:
    return {"count": KBService(KBRepository(session), session=session).count_owned(user["id"])}


@router.get("/{kb_id}", summary="查询知识库详情", response_model=ApiResponse[KBOut])
async def get_kb(
    kb_id: UUID, user: UserRow = Depends(get_current_user), session: Session = Depends(get_db)
) -> ApiResponse[KBOut]:
    kb = KBOut.model_validate(
        KBService(KBRepository(session), session=session).get_or_403(kb_id, user["id"])
    )
    return ApiResponse[KBOut](data=kb)


@router.patch("/{kb_id}", summary="更新知识库")
async def update_kb(
    kb_id: UUID,
    body: KBUpdate,
    user: UserRow = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> KBOut:
    return KBService(KBRepository(session), session=session).update(kb_id, user["id"], body)


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除知识库")
async def delete_kb(
    kb_id: UUID, user: UserRow = Depends(get_current_user), session: Session = Depends(get_db)
) -> None:
    KBService(KBRepository(session), session=session).delete(kb_id, user["id"])


# TODO(W8): 统计接口支持按时间范围过滤
