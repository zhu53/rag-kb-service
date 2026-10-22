"""mini_api.py —— Day6 任务 C：FastAPI 把 A+B 接起来"""

from typing import Any
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from json_log import reset_trace_id, set_trace_id, setup_logging
from mini_kb import ForbiddenError, KBService, NotFoundError

app = FastAPI(title="mini_kb API")

setup_logging()   # 放在模块顶层，app 创建之后

def get_current_user_id(x_user_id: str | None = Header(default=None)) -> UUID:
    # TODO 1：x_user_id 是 None 时，抛 HTTPException，状态码 401
    #   提示：raise HTTPException(status_code=?, detail="?")
    if x_user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户ID为空")

    # TODO 2：把字符串转成 UUID 并返回
    #   提示：UUID(x_user_id)
    return UUID(x_user_id)

@app.post("/kbs", status_code=201)
async def create_kb(
    body: dict,                                          # TODO A：name 从 body 里取
    user_id: UUID = Depends(get_current_user_id),
) -> dict[str, Any]:
    name = body.get("name") if isinstance(body, dict) else None
    if not name or not isinstance(name, str) or not name.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="name 是必填字符串",
        )
    name = name.strip()
    # TODO B：调 KBService().create(user_id, name)，用 to_dict() 转成 dict 返回
    return KBService().create(user_id, name).to_dict()


@app.get("/kbs")
async def list_kbs(
    page: int = 1,
    size: int = 20,
    user_id: UUID = Depends(get_current_user_id),
) -> dict[str, Any]:
    # TODO C：调 service.list(user_id, page, size)，返回 {"items": [...], "total": total}
    items, total = KBService().list(user_id, page, size)
    return {"items": [kb.to_dict() for kb in items], "total": total}

@app.exception_handler(NotFoundError)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"detail": str(exc)},
    )

@app.exception_handler(ForbiddenError)
async def forbidden_handler(request, exc):
    return JSONResponse(
        status_code=403,
        content={"detail": str(exc)},
    )

@app.get("/kbs/stats/count")
async def count_kbs(user_id: UUID = Depends(get_current_user_id)) -> dict[str, int]:
    # TODO：调 count_owned(user_id)，返回 {"count": ...}
    count = KBService().count_owned(user_id)
    return {"count": count}

@app.get("/kbs/{kb_id}")
async def get_kb(
    kb_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
) -> dict[str, Any]:
    return KBService().get_or_403(kb_id, user_id).to_dict()


@app.get("/ping")
async def ping() -> dict[str, str]:
    return {"pong": "ok"}

@app.get("/me")
async def me(user_id: UUID = Depends(get_current_user_id)) -> dict[str, str]:
    return {"user_id": str(user_id)}

@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    # TODO 1：用 uuid4 生成，别用 id()
    trace_id = str(uuid4())

    # TODO 2：set 进上下文，保存 token（用 B1 自己写的封装）
    token = set_trace_id(trace_id)

    try:
        # TODO 3：放行请求
        response = await call_next(request)

        # TODO 4：写回响应头，方便前端/网关关联日志
        response.headers["X-Trace-Id"] = trace_id
        return response
    finally:
        # TODO 5：精确恢复，避免上下文泄漏
        reset_trace_id(token)
