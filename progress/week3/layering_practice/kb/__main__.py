import tempfile
from pathlib import Path

from kb.error import ConflictError, ForbiddenError, NotFoundError
from kb.json_repo import JSONFileKBRepository
from kb.memory_repo import InMemoryKBRepository
from kb.service import KBService
from kb.tracing import setup_logging
from retry import retry  # retry.py 在 kb 包外面，平级导入

setup_logging()  # 幂等初始化：不调它，INFO 日志哪儿都不去

tmp_path = Path(tempfile.mkdtemp()) / "kbs.json"

for repo in (InMemoryKBRepository(), JSONFileKBRepository(tmp_path)):
    svc = KBService(repo)
    print(f"--- {type(repo).__name__} ---")
    kb1 = svc.create_kb("alice", "测试库")  # 成功
    svc.create_kb("alice", "第二个")  # 成功

    try:
        svc.create_kb("alice", "测试库")
    except ConflictError:
        print("同名 → ConflictError ok")

    try:
        svc.get_kb("bob", kb1["id"])
    except ForbiddenError:
        print("bob 访问别人的库 → ForbiddenError ok")

    try:
        svc.get_kb("alice", "不存在的id")
    except NotFoundError:
        print("查无此库 → NotFoundError ok")

    svc.delete_kb("alice", kb1["id"])
    try:
        svc.get_kb("alice", kb1["id"])
    except NotFoundError:
        print("delete 后 get → NotFoundError ok")

# retry 两段演示：flaky 成功（第 3 次）+ 永远失败抛最后异常
calls = {"n": 0}


@retry(times=3)
def flaky():
    calls["n"] += 1
    if calls["n"] < 3:
        raise OSError("模拟磁盘抖动")
    return "第三次成功了"


print(flaky(), "实际调用次数:", calls["n"])  # 期望：第三次成功了 实际调用次数: 3


# 全失败
@retry(times=3)
def always_fail():
    raise ValueError("no")


try:
    always_fail()
except ValueError as e:
    print("全失败 → 抛出:", e)

import threading

from kb.tracing import new_trace_id, trace_id_var

# 裸调：不经过 handle_request，上下文里没人 set 过 → 显示默认值 [--------]
KBService(InMemoryKBRepository()).create_kb("carol", "没进请求的库")


def handle_request(owner_id: str, name: str) -> None:
    """模拟 FastAPI 中间件：进门发 id，出门 reset。"""
    token = trace_id_var.set(new_trace_id())
    try:
        KBService(InMemoryKBRepository()).create_kb(owner_id, name)
    finally:
        trace_id_var.reset(token)


threads = [
    threading.Thread(target=handle_request, args=("alice", "线程1的库")),
    threading.Thread(target=handle_request, args=("bob", "线程2的库")),
]
for t in threads:
    t.start()
for t in threads:
    t.join()
