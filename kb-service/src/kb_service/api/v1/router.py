from fastapi import APIRouter

from kb_service.api.v1 import chat, documents, health, knowledge_bases

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(knowledge_bases.router, prefix="/kbs", tags=["knowledge-bases"])
api_router.include_router(documents.router, prefix="/kbs", tags=["documents"])
api_router.include_router(chat.router, tags=["chat"])
