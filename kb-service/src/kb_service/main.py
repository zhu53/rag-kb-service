from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError

from kb_service.api.v1 import health
from kb_service.api.v1.router import api_router
from kb_service.core import constants
from kb_service.core.config import get_settings
from kb_service.core.exceptions import AppError
from kb_service.core.logging import TraceMiddleware, setup_logging
from kb_service.schemas.common import ApiResponse


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs" if settings.env != "prod" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.env != "prod" else None,
        description="知识库检索服务：文档上传、切块、向量索引。",
        openapi_tags=[
            {"name": constants.TAG_HEALTH, "description": "健康检查"},
            {"name": constants.TAG_KBS, "description": "知识库"},
            {"name": constants.TAG_DOCS, "description": "文档"},
            {"name": constants.TAG_CHAT, "description": "聊天"},
        ],
    )

    app.add_middleware(TraceMiddleware)

    # ---------- 统一错误响应 ----------
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=ApiResponse(
                code=exc.http_status * 100,
                message=exc.message,
                data=exc.detail,
            ).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=ApiResponse(
                code=42200,
                message="参数校验失败",
                data=jsonable_encoder(exc.errors()),
            ).model_dump(),
        )

    # 债①（W7 遗留）：唯一约束撞车是客户端输入冲突，该 409，不该 500。
    # 真话在 exc.orig（数据库驱动的原始异常）：MySQL 说 "Duplicate entry ... for key ..."，
    # sqlite 说 "UNIQUE constraint failed: ..."——两种方言都认，其余约束错误交回默认 500。
    @app.exception_handler(IntegrityError)
    async def handle_integrity(_: Request, exc: IntegrityError) -> JSONResponse:
        raw = str(exc.orig if exc.orig is not None else exc).lower()
        if not ("duplicate" in raw or "unique" in raw):
            raise exc
        return JSONResponse(
            status_code=409,
            content=ApiResponse(
                code=40900,
                message="资源已存在或唯一字段冲突",
                data=None,
            ).model_dump(),
        )

    app.include_router(health.router, tags=[constants.TAG_HEALTH])
    app.include_router(api_router)

    # ---------- dev 专用路由（演示 token 签发）----------
    # 不进 prod：谁都能拿 token 的端点不能出现在公网应用上。
    if settings.env != "prod":
        from kb_service.api.v1 import dev

        app.include_router(dev.router, prefix="/api/v1", tags=["dev"])

    # ---------- 演示页面 ----------
    # 挂在 "/" 且必须放在所有 API 路由之后：Starlette 按注册顺序匹配，
    # 先注册的 /api/v1/* 先命中，StaticFiles 兜住剩下的（浏览器直接访问 /）。
    static_dir = Path(__file__).resolve().parents[2] / "static"
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    return app


app = create_app()
