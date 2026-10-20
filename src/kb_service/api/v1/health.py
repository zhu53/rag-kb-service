from __future__ import annotations

from fastapi import APIRouter

from kb_service.core.config import get_settings

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "env": settings.env, "version": "0.1.0"}
