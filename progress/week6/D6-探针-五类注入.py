"""D6 探针：5 类注入的爆炸时机（启动 / 请求 / 静默）。

每节独立小 app，跑一次就能看见"这个 bug 在哪一层被发现"。
运行：kb-service/.venv/Scripts/python.exe 本文件
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

print("=" * 60)
print("§1 依赖循环：启动时报还是请求时炸？")
print("=" * 60)


def get_a(_x: str = "") -> str:
    return "a"


def get_b(_y: str = "") -> str:
    return "b"


# 用 __defaults__ 造真实环（模块级 def 写不出来，因为默认值在 def 时求值）
# 注意：参数名用 _x/_y 只是占位，实际值由 Depends 注入，不参与请求参数解析
get_a.__defaults__ = (Depends(get_b),)
get_b.__defaults__ = (Depends(get_a),)

print("① 定义依赖函数：", end="")
print("没报错")
app1 = FastAPI()
print("② 创建 app：没报错")
print("③ 注册路由：", end="")
try:

    @app1.get("/cyc")
    def cyc(x: str = Depends(get_a)) -> dict:
        return {"x": x}

    print("竟然成功了")
except RecursionError:
    print("RecursionError → 注册时就炸（即 import/启动阶段，服务起不来）")

print()
print("=" * 60)
print("§2 缓存误用：默认 use_cache=True，同请求内依赖只跑一次")
print("=" * 60)

calls = {"n": 0}


def counter() -> int:
    calls["n"] += 1
    return calls["n"]


app2 = FastAPI()


@app2.get("/cached")
def cached(x: int = Depends(counter), y: int = Depends(counter)) -> dict:
    return {"x": x, "y": y, "calls": calls["n"]}


@app2.get("/uncached")
def uncached(
    x: int = Depends(counter),
    y: int = Depends(counter, use_cache=False),
) -> dict:
    return {"x": x, "y": y, "calls": calls["n"]}


c2 = TestClient(app2)
calls["n"] = 0
print("同一依赖声明两次（默认缓存）：", c2.get("/cached").json())
calls["n"] = 0
print("第二处加 use_cache=False  ：", c2.get("/uncached").json())

print()
print("=" * 60)
print("§3 middleware 顺序：谁在外面？（后 add 的在最外层）")
print("=" * 60)

order: list[str] = []


def make_mw(name: str):
    async def middleware(request, call_next):
        order.append(f"{name}-进入")
        resp = await call_next(request)
        order.append(f"{name}-退出")
        return resp

    return middleware


app3 = FastAPI()


@app3.get("/ping")
def ping() -> str:
    return "pong"


app3.middleware("http")(make_mw("A-先加"))
app3.middleware("http")(make_mw("B-后加"))

TestClient(app3).get("/ping")
print("加入顺序 A → B，实际执行顺序：", order)
print("结论：B 在外层（后加的包住先加的）")

print()
print("=" * 60)
print("§4 response_model 三种撒谎")
print("=" * 60)


class Out(BaseModel):
    id: int
    name: str


app4 = FastAPI()


@app4.get("/lie-type", response_model=Out)
def lie_type() -> dict:
    return {"id": "不是数字", "name": "x"}  # 撒谎①：类型不符


@app4.get("/lie-missing", response_model=Out)
def lie_missing() -> dict:
    return {"id": 1}  # 撒谎②：必填字段缺失


@app4.get("/lie-extra", response_model=Out)
def lie_extra() -> dict:
    return {"id": 1, "name": "x", "secret": "本该给前端的关键字段"}  # 撒谎③：多字段被静默丢


c4 = TestClient(app4, raise_server_exceptions=False)
print("① 类型不符   →", c4.get("/lie-type").status_code)
print("② 字段缺失   →", c4.get("/lie-missing").status_code)
r = c4.get("/lie-extra")
print("③ 多余字段   →", r.status_code, r.json(), "← 零症状，字段静默消失")

print()
print("=" * 60)
print("§5 校验放宽：Field(le=100) 被删掉后，请求还拦得住吗")
print("=" * 60)


class ParamsLoose(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1)  # 原来的 le=100 被"顺手放宽"


app5 = FastAPI()


@app5.get("/list")
def list_loose(params: ParamsLoose = Depends()) -> dict:
    return {"page": params.page, "size": params.size}


c5 = TestClient(app5)
for qs in ("?size=50", "?size=500", "?size=100000"):
    r = c5.get("/list" + qs)
    print(f"{qs:>12} → {r.status_code} {r.json() if r.status_code == 200 else ''}")
print("结论：约束删掉后请求全部放行，只有『有边界测试』才能发现")
