from fastapi import APIRouter, Depends

from kb_service.api.deps import get_current_user
from kb_service.api.v1 import admin, auth, chat, documents, knowledge_bases
from kb_service.core import constants

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(
    knowledge_bases.router,
    prefix="/kbs",
    tags=[constants.TAG_KBS],
    dependencies=[Depends(get_current_user)],
)
api_router.include_router(
    documents.router,
    prefix="/kbs",
    tags=[constants.TAG_DOCS],
    dependencies=[Depends(get_current_user)],
)
api_router.include_router(
    chat.router,
    tags=[constants.TAG_CHAT],
    dependencies=[Depends(get_current_user)],
)
api_router.include_router(
    auth.router,
    tags=[constants.TAG_AUTH],
)
api_router.include_router(
    admin.router,
    prefix="/admin",
    tags=[constants.TAG_ADMIN],
    # 不在 router 上挂 require_role：admin.py 里逐路由声明，便于拿到 admin 行
    # （将来"不能封自己"要用）。两条路都靠依赖缓存，查库次数一样。
)
