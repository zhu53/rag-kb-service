from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from kb_service.api.deps import get_current_user_id
from kb_service.schemas.kb import KBCreate, KBOut, KBUpdate, Page
from kb_service.services.kb_service import KBService

router = APIRouter()


@router.post("", status_code=status.HTTP_201_CREATED, summary="创建知识库")
async def create_kb(
    body: KBCreate,
    user_id: UUID = Depends(get_current_user_id),
) -> KBOut:
    return KBService().create(user_id, body)


@router.get("", summary="分页查询我的知识库")
async def list_kbs(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    user_id: UUID = Depends(get_current_user_id),
) -> Page[KBOut]:
    return KBService().list(user_id, page, size)


@router.get("/stats/count", summary="我的知识库总数")
async def count_kbs(user_id: UUID = Depends(get_current_user_id)) -> dict[str, int]:
    return {"count": KBService().count_owned(user_id)}


@router.get("/{kb_id}", summary="查询知识库详情")
async def get_kb(kb_id: UUID, user_id: UUID = Depends(get_current_user_id)) -> KBOut:
    return KBOut.model_validate(KBService().get_or_403(kb_id, user_id))


@router.patch("/{kb_id}", summary="更新知识库")
async def update_kb(
    kb_id: UUID,
    body: KBUpdate,
    user_id: UUID = Depends(get_current_user_id),
) -> KBOut:
    return KBService().update(kb_id, user_id, body)


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除知识库")
async def delete_kb(kb_id: UUID, user_id: UUID = Depends(get_current_user_id)) -> None:
    KBService().delete(kb_id, user_id)


# TODO: 统计接口后续支持按时间范围过滤（wb）/后续支持按时间范围过滤
