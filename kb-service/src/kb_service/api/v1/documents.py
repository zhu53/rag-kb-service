from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from kb_service.api.deps import get_current_user_id
from kb_service.core.db import get_db
from kb_service.repositories.doc_repo import DocRepository
from kb_service.schemas.common import PageParams
from kb_service.schemas.doc import DocCreate, DocOut
from kb_service.schemas.kb import Page
from kb_service.services.doc_service import DocService
from kb_service.services.indexing import run_index

router = APIRouter()


@router.post("/{kb_id}/documents", status_code=status.HTTP_201_CREATED, summary="新增文档")
async def create_doc(
    kb_id: UUID,
    body: DocCreate,
    background_tasks: BackgroundTasks,
    user_id: UUID = Depends(get_current_user_id),
    session: Session = Depends(get_db),
) -> DocOut:
    doc = DocService(DocRepository(session), session=session).create(kb_id, user_id, body)
    background_tasks.add_task(run_index, doc.id, body.content)
    return doc


@router.get("/{kb_id}/documents", summary="分页查询知识库下的文档")
async def list_docs(
    kb_id: UUID,
    params: Annotated[PageParams, Depends()],
    user_id: UUID = Depends(get_current_user_id),
    session: Session = Depends(get_db),
) -> Page[DocOut]:
    return DocService(DocRepository(session), session=session).list(
        kb_id, user_id, params.page, params.size
    )


@router.get("/{kb_id}/documents/{doc_id}", summary="文档详情")
async def get_doc(
    kb_id: UUID,
    doc_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    session: Session = Depends(get_db),
) -> DocOut:
    return DocService(DocRepository(session), session=session).get(doc_id, user_id)


@router.delete(
    "/{kb_id}/documents/{doc_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除文档",
)
async def delete_doc(
    kb_id: UUID,
    doc_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    session: Session = Depends(get_db),
) -> None:
    DocService(DocRepository(session), session=session).delete(doc_id, user_id)
