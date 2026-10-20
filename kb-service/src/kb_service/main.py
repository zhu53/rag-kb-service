from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from kb_service.api.v1.router import api_router
from kb_service.core.config import get_settings
from kb_service.core.exceptions import AppError
from kb_service.core.logging import TraceMiddleware, setup_logging


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
            content={"code": exc.code, "message": exc.message, "detail": exc.detail},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "code": "VALIDATION_ERROR",
                "message": "参数校验失败",
                "detail": exc.errors(),
            },
        )

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
