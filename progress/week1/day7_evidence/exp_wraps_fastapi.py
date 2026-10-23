"""Q4 证据：装饰器不加 @wraps，FastAPI 路由会直接 422。

跑法（在 kb-service 目录）：
    .venv/Scripts/python.exe ../progress/week1/day7_evidence/exp_wraps_fastapi.py

预期输出关键行：
    __name__: wrapper wrapper route_c
    __doc__: None
    /a operationId='wrapper_a_get' summary='Wrapper' description=None
    GET /a 带 token: {'detail': [{'type': 'missing', 'loc': ['query', 'args'], ...}]}
    GET /c（带 wraps）: {'user': 'alice'}
"""

from functools import wraps

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

app = FastAPI()


def need_auth(x_token: str = "anon") -> str:
    """假鉴权依赖：从请求头取一个值。"""
    return x_token


def logger_without_wraps(fn):
    """忘了加 @wraps 的日志装饰器。"""

    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)

    return wrapper


def logger_with_wraps(fn):
    """正确写法：@wraps 保留原函数的 __name__ / __doc__ / __wrapped__。"""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)

    return wrapper


@app.get("/a")
@logger_without_wraps
def route_a(user: str = Depends(need_auth)) -> dict[str, str]:
    """A 接口：有依赖注入，但装饰器丢了签名。"""
    return {"user": user}


@app.get("/c")
@logger_with_wraps
def route_c(user: str = Depends(need_auth)) -> dict[str, str]:
    """C 接口：对照组，签名完整。"""
    return {"user": user}


def main() -> None:
    print("__name__:", route_a.__name__, route_c.__name__)
    print("__doc__:", repr(route_a.__doc__))
    print("有没有 __wrapped__:", hasattr(route_a, "__wrapped__"))

    spec = app.openapi()
    for path in ("/a", "/c"):
        op = spec["paths"][path]["get"]
        print(
            f"{path} operationId={op.get('operationId')!r} "
            f"summary={op.get('summary')!r} description={op.get('description')!r}"
        )

    client = TestClient(app)
    print("GET /a（无 wraps）:", client.get("/a", headers={"x-token": "alice"}).json())
    print("GET /c（有 wraps）:", client.get("/c", headers={"x-token": "alice"}).json())


if __name__ == "__main__":
    main()
