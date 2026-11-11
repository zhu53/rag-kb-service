from fastapi import APIRouter, Depends

from kb_service.api.deps import get_current_user_id
from kb_service.api.v1 import chat, documents, knowledge_bases
from kb_service.core import constants

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(
    knowledge_bases.router,
    prefix="/kbs",
    tags=[constants.TAG_KBS],
    dependencies=[Depends(get_current_user_id)],
)
api_router.include_router(
    documents.router,
    prefix="/kbs",
    tags=[constants.TAG_DOCS],
    dependencies=[Depends(get_current_user_id)],
)
api_router.include_router(
    chat.router,
    tags=[constants.TAG_CHAT],
    dependencies=[Depends(get_current_user_id)],
)
