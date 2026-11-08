"""D2 教材配套探针：一次跑完，产出教材第四~八节引用的全部实测输出。

跑法（在 kb-service 下，用项目锁定的 Python 3.11 解释器）：

    # Windows PowerShell
    & .\\.venv\\Scripts\\python.exe ..\\progress\\week6\\D2-探针.py

    # Git Bash / Linux / macOS
    ./.venv/Scripts/python.exe ../progress/week6/D2-探针.py

输出里每个块以 [编号] 开头，编号与教材里的引用一一对应（清单见教材 §4.1）。
中间件叫 A，只在两个位置打点：
    "A>"            进入 A（call_next 之前）
    "<A <status>"   拿到响应（call_next 之后）
walk_through 组的 A 还会在 except 里多记一条 "A 捕获到 <类型>"。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import BaseModel, field_validator
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint


# ---------------------------------------------------------------- 公共零件

log: list[str] = []


class NotFoundError(Exception):
    """模拟项目里的 AppError 子类。"""


class Payload(BaseModel):
    """探针 H 用的请求体模型，必须定义在模块级（局部类会让 FastAPI 解析不出 body）。"""

    x: int

    @field_validator("x")
    @classmethod
    def _check(cls, v: int) -> int:
        if v > 10:
            raise ValueError("x 不能大于 10")
        return v


class A(BaseHTTPMiddleware):
    """打点中间件。log_catch=True 时，额外在 except 分支记一条（模拟 TraceMiddleware）。"""

    log_catch: bool = False

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        log.append("A>")
        try:
            resp = await call_next(request)
        except Exception as exc:
            if self.log_catch:
                log.append(f"A 捕获到 {type(exc).__name__}")
            raise
        log.append(f"<A {resp.status_code}")
        return resp


def make_app(*, wildcard: bool = False, log_catch: bool = False) -> FastAPI:
    """wildcard=True 时注册 @app.exception_handler(Exception)（源码会把它拎到最外层）。"""
    app = FastAPI()
    A.log_catch = log_catch
    app.add_middleware(A)

    @app.exception_handler(NotFoundError)
    async def _not_found(_: Request, __: NotFoundError) -> Response:
        return Response(content='{"code":"NOT_FOUND"}', status_code=404,
                        media_type="application/json")

    if wildcard:

        @app.exception_handler(Exception)
        async def _wildcard(_: Request, exc: Exception) -> Response:
            log.append(f"通配 handler 收到 {type(exc).__name__}")
            return Response(content='{"code":"INTERNAL"}', status_code=500,
                            media_type="application/json")

    @app.get("/ok")
    def ok() -> dict[str, str]:
        return {"ok": "1"}

    @app.get("/app-error")
    def app_error() -> None:
        raise NotFoundError("kb 不存在")

    @app.get("/teapot")
    def teapot() -> None:
        raise HTTPException(status_code=418, detail="teapot")

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("炸了")

    return app


def show(tag: str, desc: str, *, status: int | None = None, body: Any = None) -> None:
    parts = [f"log: {log}"]
    if status is not None:
        parts.append(f"status: {status}")
    if body is not None:
        parts.append(f"body: {body}")
    print(f"[{tag}] {desc}")
    print("    " + " | ".join(parts))
    print()
    log.clear()


# ---------------------------------------------------------------- A~F：异常三条路

def probe_a_to_f() -> None:
    # 必须关掉 raise_server_exceptions，否则 /boom 会把原异常直接抛给调用方（见探针 K）
    with TestClient(make_app(), raise_server_exceptions=False) as c:
        r = c.get("/ok")
        show("A", "正常请求（对照组）", status=r.status_code, body=r.text)

        r = c.get("/app-error")
        show("B", "路由抛 AppError 子类", status=r.status_code, body=r.json())

        r = c.get("/teapot")
        show("C", "路由抛 HTTPException(418)", status=r.status_code, body=r.json())

        r = c.get("/boom")
        show("D", "路由抛 RuntimeError（没注册通配 handler）", status=r.status_code, body=r.text)

        r = c.get("/nope")
        show("F", "路由不存在（框架自己抛 404）", status=r.status_code, body=r.json())


# ---------------------------------------------------------------- E：直连 ASGI

def probe_e() -> None:
    app = make_app()
    sent: list[dict[str, Any]] = []
    caught: list[str] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/boom",
        "raw_path": b"/boom",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver")],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }

    async def main() -> None:
        try:
            await app(scope, receive, send)
        except Exception as exc:  # noqa: BLE001 - 探针就是要看它冒出来
            caught.append(type(exc).__name__)

    asyncio.run(main())
    kinds = [m["type"] for m in sent]
    status = next((m["status"] for m in sent if m["type"] == "http.response.start"), None)
    print("[E] 绕过 TestClient，直接调 ASGI（等价于 uvicorn 视角）")
    print(f"    已发出的 ASGI 消息: {kinds} | status: {status} | 冒到 ASGI 层的异常: {caught}")
    print()
    log.clear()


# ---------------------------------------------------------------- G：中间件读 body

def probe_g() -> None:
    class ReadBody(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
            if request.method == "POST":
                log.append(f"BodyReader 读到 {await request.body()!r}")
            return await call_next(request)

    app = FastAPI()
    app.add_middleware(ReadBody)

    @app.post("/echo")
    async def echo(request: Request) -> dict[str, str]:
        log.append(f"handler 读到 {await request.body()!r}")
        return {"a": "1"}

    with TestClient(app) as c:
        r = c.post("/echo", json={"a": 1})
    show("G", "中间件先读 body，再 call_next", status=r.status_code, body=r.json())


# ---------------------------------------------------------------- M / N：能不能改状态码

def probe_m_n() -> None:
    class BaseChange(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
            resp = await call_next(request)
            resp.status_code = 418
            resp.headers["x-added"] = "1"
            return resp

    app = FastAPI()
    app.add_middleware(BaseChange)

    @app.get("/plain")
    def plain() -> dict[str, str]:
        return {"a": "1"}

    with TestClient(app) as c:
        r = c.get("/plain")
        log.append(f"x-added: {r.headers.get('x-added')}")
        log.append(f"status_code 改成 418 后，客户端看到 {r.status_code}")
        show("M", "BaseHTTPMiddleware：call_next 返回后改 status_code / 加 header", body=r.json())

    class PureAsgi:
        def __init__(self, inner: Any, mode: str) -> None:
            self.inner = inner
            self.mode = mode

        async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
            if scope["type"] != "http":
                await self.inner(scope, receive, send)
                return
            if self.mode == "buffer":            # 先攒着，改完再统一转发
                msgs: list[dict[str, Any]] = []

                async def capture(m: dict[str, Any]) -> None:
                    msgs.append(m)

                await self.inner(scope, receive, capture)
                for m in msgs:
                    if m["type"] == "http.response.start":
                        m["status"] = 418
                    await send(m)
            else:                                 # 边收边转发，start 已经出去了
                held: dict[str, Any] = {}

                async def forward(m: dict[str, Any]) -> None:
                    if m["type"] == "http.response.start":
                        held.update(m)
                    await send(m)

                await self.inner(scope, receive, forward)
                held["status"] = 418              # 事后改，无效

    for mode in ("buffer", "forward"):
        app2 = FastAPI()
        app2.add_middleware(PureAsgi, mode=mode)

        @app2.get("/plain")
        def plain2() -> dict[str, str]:
            return {"a": "1"}

        with TestClient(app2) as c:
            r2 = c.get("/plain")
        log.append(f"{mode} 模式，客户端看到 {r2.status_code}")
    show("N", "纯 ASGI 中间件：转发 start 之前改有效，之后改无效")


# ---------------------------------------------------------------- H：校验失败能不能序列化

def probe_h() -> None:
    def build(*, encode: bool) -> FastAPI:
        app = FastAPI()

        @app.exception_handler(RequestValidationError)
        async def _invalid(_: Request, exc: RequestValidationError) -> Response:
            payload = exc.errors()
            kinds = [type(e.get("ctx", {}).get("error")).__name__ for e in payload]
            log.append(f"errors() 里 ctx.error 的类型: {kinds}")
            data = jsonable_encoder(payload) if encode else payload
            return Response(content=json.dumps(data), status_code=422,
                            media_type="application/json")

        @app.post("/items")
        def create(p: Payload) -> dict[str, int]:
            return {"x": p.x}

        return app

    for encode in (False, True):
        tag = "H-fixed" if encode else "H-broken"
        desc = "先 jsonable_encoder(errors()) 再序列化" if encode else "handler 直接 json.dumps(exc.errors())"
        with TestClient(build(encode=encode), raise_server_exceptions=False) as c:
            r = c.post("/items", json={"x": 99})
        show(tag, desc, status=r.status_code, body=r.text[:120])


# ---------------------------------------------------------------- I / J：有没有通配 handler

def probe_i_j() -> None:
    with TestClient(make_app(wildcard=False, log_catch=True), raise_server_exceptions=False) as c:
        r = c.get("/boom")
        show("I", "没注册通配 handler", status=r.status_code, body=r.text)

    with TestClient(make_app(wildcard=True, log_catch=True), raise_server_exceptions=False) as c:
        r = c.get("/boom")
        show("J", "注册了 @app.exception_handler(Exception)", status=r.status_code, body=r.text)


# ---------------------------------------------------------------- K：TestClient 默认会抛

def probe_k() -> None:
    with TestClient(make_app()) as c:      # 默认 raise_server_exceptions=True
        try:
            c.get("/boom")
        except RuntimeError as exc:
            log.append(f"TestClient 把原异常抛给了测试代码: {type(exc).__name__}")
    show("K", "TestClient 默认 raise_server_exceptions=True")


# ---------------------------------------------------------------- L：request.state 传值

def probe_l() -> None:
    class SetState(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
            request.state.trace_id = "t-123"
            return await call_next(request)

    app = FastAPI()
    app.add_middleware(SetState)

    @app.get("/who")
    def who(request: Request) -> dict[str, str]:
        log.append(f"路由读到 request.state.trace_id = {request.state.trace_id}")
        return {"trace_id": request.state.trace_id}

    with TestClient(app) as c:
        r = c.get("/who")
    show("L", "中间件写 request.state，路由读", status=r.status_code, body=r.json())


if __name__ == "__main__":
    probe_a_to_f()
    probe_e()
    probe_g()
    probe_m_n()
    probe_h()
    probe_i_j()
    probe_k()
    probe_l()
