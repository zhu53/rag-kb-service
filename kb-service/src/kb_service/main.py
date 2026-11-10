from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from kb_service.api.v1 import health
from kb_service.api.v1.router import api_router
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

    app.include_router(health.router, tags=["health"])
    app.include_router(api_router)
    return app


app = create_app()
