"""W6-D5 探针：OpenAPI 定制 + BackgroundTasks 行为实测。

跑法（kb-service 下）：
    .\.venv\Scripts\python.exe ..\progress\week6\D5-探针-OpenAPI与BackgroundTasks.py
"""

from __future__ import annotations

import threading
import time
from typing import Annotated

from fastapi import BackgroundTasks, Depends, FastAPI
from fastapi.testclient import TestClient

LINE = "-" * 70


def section(title: str) -> None:
    print(f"\n{LINE}\n{title}\n{LINE}")


# ============================================================
# 一、OpenAPI 元数据：拼错了会怎样
# ============================================================
section("一、openapi_tags 名字拼错 → 静默失效")

app1 = FastAPI(
    title="KB Service",
    version="0.1.0",
    openapi_tags=[
        {"name": "knowledge-bases", "description": "知识库的增删改查"},
        {"name": "documents", "description": "文档上传与解析"},
        {"name": "share", "description": "分享（故意写错：真实 tag 是 shares）"},
    ],
)


@app1.get("/kbs", tags=["knowledge-bases"])
def list_kbs() -> list[str]:
    return []


@app1.get("/kbs/{kb_id}/docs", tags=["documents"])
def list_docs(kb_id: str) -> list[str]:
    return []


@app1.get("/shares", tags=["shares"])
def list_shares() -> list[str]:
    return []


spec1 = app1.openapi()
print("tags 段（按 openapi_tags 声明顺序）:")
for t in spec1["tags"]:
    print(f"  name={t['name']!r:20} desc={t.get('description', '<无>')}")
print("\n每个路径实际用的 tag:")
for path, ops in spec1["paths"].items():
    for method, op in ops.items():
        print(f"  {method.upper():6} {path:22} tags={op.get('tags')}")
print("\n结论：声明了 'share' 却没有任何路由用它 → tags 里仍然出现，但没路由归属；")
print("      路由用了 'shares' 却未声明 → 自动出现在 tags 里但没有 description。")
print("      → 两边都不报错，只在 /docs 里露馅。")

# ============================================================
# 二、路由级文档字段：summary / description / response_description / deprecated
# ============================================================
section("二、路由级文档字段怎么写进 OpenAPI")


@app1.post(
    "/kbs",
    tags=["knowledge-bases"],
    summary="创建知识库（一行摘要）",
    description="多行说明，支持 **Markdown**：\n\n- 列表项一\n- 列表项二",
    response_description="创建成功，返回知识库本体",
    deprecated=False,
    status_code=201,
)
def create_kb() -> dict[str, str]:
    return {"id": "1"}


@app1.get("/old", tags=["documents"], deprecated=True, summary="旧接口，别用了")
def old_api() -> dict[str, str]:
    return {}


spec1 = app1.openapi()
op = spec1["paths"]["/kbs"]["post"]
print("POST /kbs 的 openapi 片段:")
for k in ("summary", "description", "responses", "deprecated"):
    print(f"  {k}: {op.get(k)}")
print("\nGET /old deprecated 字段:", spec1["paths"]["/old"]["get"].get("deprecated"))

# ============================================================
# 三、include_in_schema=False：藏起来但还能调
# ============================================================
section("三、include_in_schema=False")


@app1.get("/internal/stats", include_in_schema=False)
def internal_stats() -> dict[str, int]:
    return {"qps": 0}


print("路径表里有 /internal/stats 吗:", "/internal/stats" in app1.openapi()["paths"])
c1 = TestClient(app1)
print("实际能调通吗:", c1.get("/internal/stats").status_code, c1.get("/internal/stats").json())

# ============================================================
# 四、自定义 openapi()：加全局 security / servers，以及缓存陷阱
# ============================================================
section("四、自定义 openapi() 与 app.openapi_schema 缓存")

app2 = FastAPI(title="Cached", version="1.0.0")
call_count = {"n": 0}


@app2.get("/ping")
def ping() -> str:
    return "pong"


base_openapi = app2.openapi  # ← 关键：先把原方法存下来


def custom_openapi() -> dict:
    call_count["n"] += 1
    if app2.openapi_schema:
        return app2.openapi_schema
    schema = base_openapi()  # 不能写 app2.openapi()：那已经是 custom_openapi 自己 → 无限递归
    schema.setdefault("servers", []).append({"url": "https://api.example.com", "description": "生产"})
    app2.openapi_schema = schema
    return schema


app2.openapi = custom_openapi  # type: ignore[method-assign]
c2 = TestClient(app2)
c2.get("/openapi.json")
c2.get("/openapi.json")
c2.get("/openapi.json")
print(f"custom_openapi 调用次数（3 次请求后）: {call_count['n']}")
print("servers:", c2.get('/openapi.json').json().get("servers"))

# ============================================================
# 五、docs_url / openapi_url 关闭
# ============================================================
section("五、生产环境关文档")
app3 = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
c3 = TestClient(app3)
print("docs:", c3.get("/docs").status_code, "| openapi:", c3.get("/openapi.json").status_code)

# ============================================================
# 六、BackgroundTasks：时序 / 异常 / 线程 / 顺序
# ============================================================
section("六、BackgroundTasks 行为")
app4 = FastAPI()
events: list[str] = []


def bg_sync(name: str) -> None:
    events.append(f"{name} start")
    time.sleep(0.2)
    events.append(f"{name} end")


async def bg_async(name: str) -> None:
    events.append(f"{name} start(async)")
    events.append(f"{name} end(async)")


@app4.get("/bg")
def with_bg(background_tasks: BackgroundTasks) -> dict[str, str]:
    background_tasks.add_task(bg_sync, "sync")
    background_tasks.add_task(bg_async, "async")
    events.append("handler 返回")
    return {"ok": "1"}


@app4.get("/bg-thread")
def bg_thread(background_tasks: BackgroundTasks) -> dict[str, str]:
    def job() -> None:
        events.append(f"线程名={threading.current_thread().name}")

    background_tasks.add_task(job)
    return {"ok": "1"}


c4 = TestClient(app4)
events.clear()
t0 = time.perf_counter()
r = c4.get("/bg")
elapsed = time.perf_counter() - t0
print(f"响应状态={r.status_code} body={r.json()} 客户端总耗时={elapsed:.3f}s")
print("事件顺序:", events)
print("→ 客户端拿到响应头/体之后，任务才跑；但 TestClient 会等整个 ASGI 调用结束再返回，")
print("  所以耗时把 0.2s 算进去了——真实 uvicorn 下客户端早已收到响应。")

events.clear()
c4.get("/bg-thread")
print("\n同步任务的线程:", events)

section("七、后台任务抛异常会怎样")
app5 = FastAPI()


def boom() -> None:
    raise RuntimeError("后台任务炸了")


@app5.get("/boom")
def boom_route(background_tasks: BackgroundTasks) -> dict[str, str]:
    background_tasks.add_task(boom)
    return {"ok": "响应先发出"}


c5 = TestClient(app5, raise_server_exceptions=False)
r5 = c5.get("/boom")
print("客户端看到的状态码:", r5.status_code, "body:", r5.json())
print("→ 响应已发出，异常发生在发送之后：客户端无法得知，只在服务端日志里留 traceback。")

c5_raise = TestClient(app5)
try:
    c5_raise.get("/boom")
except RuntimeError as exc:
    print("raise_server_exceptions=True（TestClient 默认）会直接抛出:", exc)

section("八、BackgroundTasks 在依赖里注入")
app6 = FastAPI()
dep_events: list[str] = []


def dep(background_tasks: BackgroundTasks) -> None:
    background_tasks.add_task(dep_events.append, "来自依赖")


@app6.get("/dep-bg")
def dep_bg(_: Annotated[None, Depends(dep)]) -> dict[str, str]:
    return {"ok": "1"}


c6 = TestClient(app6)
c6.get("/dep-bg")
print("依赖里加的任务执行了吗:", dep_events)

section("九、204 + BackgroundTasks 能共存吗")
app7 = FastAPI()


@app7.delete("/thing", status_code=204)
def delete_thing(background_tasks: BackgroundTasks) -> None:
    background_tasks.add_task(dep_events.append, "204 之后")


c7 = TestClient(app7)
r7 = c7.delete("/thing")
print("状态码:", r7.status_code, "| 响应体:", repr(r7.content), "| 任务执行:", dep_events[-1:])

section("十、源码规模")
import inspect

import starlette.background as sb

src = inspect.getsource(sb)
print("starlette/background.py 行数:", len(src.splitlines()))
print("=" * 30, "全文", "=" * 30)
print(src)
