"""W6-D5 探针 2：BackgroundTasks 时序精确验证 + 中间件耗时 + 错误文档化。"""

from __future__ import annotations

import time

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

LINE = "-" * 70


def section(t: str) -> None:
    print(f"\n{LINE}\n{t}\n{LINE}")


# ============================================================
# 一、响应到底先发还是任务先跑（带时间戳）
# ============================================================
section("一、http.response.body 发送时刻 vs 后台任务启动时刻")

marks: list[tuple[str, float]] = []


class StampMiddleware:
    """纯 ASGI 中间件：在 body 发出去的那一刻打时间戳。"""

    def __init__(self, app):  # noqa: ANN001
        self.app = app

    async def __call__(self, scope, receive, send):  # noqa: ANN001
        async def send_wrapper(message):  # noqa: ANN001
            if message["type"] == "http.response.body":
                marks.append(("body 已发送", time.perf_counter()))
            await send(message)

        await self.app(scope, receive, send_wrapper)


app1 = FastAPI()
app1.add_middleware(StampMiddleware)


def job() -> None:
    marks.append(("任务启动", time.perf_counter()))
    time.sleep(0.05)
    marks.append(("任务结束", time.perf_counter()))


@app1.get("/bg")
def bg(background_tasks: BackgroundTasks) -> dict[str, str]:
    marks.append(("handler 返回前", time.perf_counter()))
    background_tasks.add_task(job)
    return {"ok": "1"}


c1 = TestClient(app1)
marks.clear()
c1.get("/bg")
t0 = marks[0][1]
for name, t in marks:
    print(f"  {name:12} +{(t - t0) * 1000:7.2f} ms")

# ============================================================
# 二、中间件记的耗时含不含后台任务
# ============================================================
section("二、中间件耗时 vs 后台任务")


class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # noqa: ANN001
        t = time.perf_counter()
        response = await call_next(request)
        cost = (time.perf_counter() - t) * 1000
        print(f"  [中间件] call_next 前后耗时 = {cost:.2f} ms（任务里 sleep 300ms）")
        return response


app2 = FastAPI()
app2.add_middleware(TimingMiddleware)


def slow_job() -> None:
    time.sleep(0.3)


@app2.get("/slow-bg")
def slow_bg(background_tasks: BackgroundTasks) -> dict[str, str]:
    background_tasks.add_task(slow_job)
    return {"ok": "1"}


c2 = TestClient(app2)
t0 = time.perf_counter()
c2.get("/slow-bg")
print(f"  [客户端] 总耗时 = {(time.perf_counter() - t0) * 1000:.2f} ms")

# ============================================================
# 三、handler 抛异常 → 后台任务还跑吗
# ============================================================
section("三、handler 抛异常后，已注册的后台任务执行吗")

app3 = FastAPI()
ran: list[str] = []


def mark() -> None:
    ran.append("跑了")


class MyError(Exception):
    pass


@app3.get("/raise")
def raise_after_add(background_tasks: BackgroundTasks) -> dict[str, str]:
    background_tasks.add_task(mark)
    raise MyError("业务异常")


@app3.exception_handler(MyError)
async def handle_my_error(request: Request, exc: MyError):  # noqa: ANN001
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=400, content={"error": "handled"})


c3 = TestClient(app3)
r3 = c3.get("/raise")
print("  响应:", r3.status_code, r3.json(), "| 任务执行记录:", ran or "（空）——没跑")

# ============================================================
# 四、把统一响应壳写进 OpenAPI：responses 参数
# ============================================================
section("四、responses= 文档化统一错误壳")

app4 = FastAPI(title="Doc Error Contract")


class ApiResponse(BaseModel):
    code: int = 0
    message: str = "ok"
    data: object | None = None


@app4.get(
    "/items/{item_id}",
    responses={
        401: {"model": ApiResponse, "description": "未认证（code=40100）"},
        404: {"model": ApiResponse, "description": "资源不存在（code=40400）"},
    },
)
def get_item(item_id: int) -> dict[str, int]:
    return {"id": item_id}


spec = app4.openapi()
resp = spec["paths"]["/items/{item_id}"]["get"]["responses"]
for code in ("200", "401", "404"):
    body = resp[code]
    schema_ref = body.get("content", {}).get("application/json", {}).get("schema", {})
    print(f"  {code}: desc={body.get('description')!r} schema={schema_ref}")
print("  components 里的模型名:", [k for k in spec.get("components", {}).get("schemas", {})])

# ============================================================
# 五、自定义 openapi()：函数被调用几次 / 真正构建几次
# ============================================================
section("五、缓存：调用次数 vs 构建次数")

app5 = FastAPI(title="Cache")
builds = {"n": 0}
calls = {"n": 0}


@app5.get("/x")
def x() -> str:
    return "x"


base = app5.openapi


def counting_base() -> dict:
    builds["n"] += 1
    return base()


def custom() -> dict:
    calls["n"] += 1
    if app5.openapi_schema:
        return app5.openapi_schema
    schema = counting_base()
    schema["info"]["x-team"] = "kb-service"
    app5.openapi_schema = schema
    return schema


app5.openapi = custom  # type: ignore[method-assign]
c5 = TestClient(app5)
for _ in range(3):
    c5.get("/openapi.json")
print(f"  custom 函数被调用 {calls['n']} 次（3 次请求）")
print(f"  schema 真正构建 {builds['n']} 次")
print("  自定义字段生效:", c5.get("/openapi.json").json()["info"].get("x-team"))
