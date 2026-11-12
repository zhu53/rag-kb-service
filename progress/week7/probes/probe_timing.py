from fastapi import BackgroundTasks, Depends, FastAPI
from fastapi.testclient import TestClient

log: list[str] = []
app = FastAPI()


def get_db():
    log.append("1. 依赖开始：拿 session")
    yield "SESSION"
    log.append("4. 依赖收尾：关 session")


@app.get("/x")
def x(bg: BackgroundTasks, db: str = Depends(get_db)):
    log.append("2. handler 执行")
    bg.add_task(lambda: log.append("5. 后台任务执行"))
    return {"db": db}


@app.middleware("http")
async def mw(request, call_next):
    log.append("0. 中间件进入")
    r = await call_next(request)
    log.append("3. 中间件拿到响应（响应体已生成）")
    return r


c = TestClient(app)
print(c.get("/x").json())
print("\n".join(log))
