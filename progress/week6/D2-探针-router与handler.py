"""探针：⑤ Router（匹配）与 ⑥ deps+handler（执行）的真实边界。

验证四件事：
1. 404 时依赖跑不跑
2. 405 时依赖跑不跑
3. 422（query 类型错）时依赖跑不跑
4. 422（body 校验失败）时依赖跑不跑、body 读没读
"""

from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import BaseModel

log: list[str] = []


def dep_track() -> str:
    """有副作用的依赖：只用来观察它有没有被调用。"""
    log.append("dep_track 执行")
    return "追踪值"


class Payload(BaseModel):
    x: int


app = FastAPI()


@app.get("/plain")
def plain(v: Annotated[str, Depends(dep_track)]) -> dict[str, str]:
    log.append("handler 执行")
    return {"v": v}


@app.get("/with-body")
def with_body(v: Annotated[str, Depends(dep_track)], p: Payload | None = None) -> dict[str, str]:
    log.append("with-body handler 执行")
    return {"v": v}


@app.post("/post-only")
def post_only(v: Annotated[str, Depends(dep_track)]) -> dict[str, str]:
    return {"v": v}


@app.get("/with-query")
def with_query(n: int, v: Annotated[str, Depends(dep_track)]) -> dict[str, str]:
    return {"v": v, "n": str(n)}


def probe(label: str, fn) -> None:
    log.clear()
    r = fn()
    print(f"[{label}] status={r.status_code} | 依赖跑了吗={'是' if log else '否'} | log={log}")


with TestClient(app) as c:
    probe("正常", lambda: c.get("/plain"))
    probe("404 路径不存在", lambda: c.get("/nope"))
    probe("405 方法不对", lambda: c.get("/post-only"))
    probe("422 query 类型错", lambda: c.get("/with-query?n=abc"))
    probe("422 body 校验失败", lambda: c.request("GET", "/with-body", json={"x": "not-int"}))
    probe("200 body 正常", lambda: c.request("GET", "/with-body", json={"x": 1}))

print()
print("=== include_router 是扁平化还是嵌套 ===")
from fastapi import APIRouter

parent = FastAPI()
child = APIRouter()


@child.get("/inner")
def inner() -> dict[str, str]:
    return {"a": "1"}


before = len(parent.routes)
parent.include_router(child, prefix="/api")
after = len(parent.routes)
print(f"include 前 routes={before}，后={after}")
print("最后一层的类型链:", " -> ".join(t.__name__ for t in type(parent.routes[-1]).__mro__[:3]))
print("是否存在嵌套 Router 对象:", any(type(r).__name__ == "Router" for r in parent.routes))
print("合并进来的路径:", [getattr(r, "path", None) for r in parent.routes if "inner" in getattr(r, "path", "")])
