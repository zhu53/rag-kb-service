import tempfile
from pathlib import Path

from retry import retry                      # retry.py 在 kb 包外面，平级导入
from kb.service import KBService
from kb.memory_repo import InMemoryKBRepository
from kb.json_repo import JSONFileKBRepository
from kb.error import ConflictError, NotFoundError, ForbiddenError

tmp_path = Path(tempfile.mkdtemp()) / "kbs.json"

for repo in (InMemoryKBRepository(), JSONFileKBRepository(tmp_path)):
    svc = KBService(repo)
    print(f"--- {type(repo).__name__} ---")
    kb1 = svc.create_kb("alice", "测试库")    # 成功
    svc.create_kb("alice", "第二个")          # 成功

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

print(flaky(), "实际调用次数:", calls["n"])   # 期望：第三次成功了 实际调用次数: 3
#全失败
@retry(times=3)
def always_fail():
    raise ValueError("no")

try:
    always_fail()
except ValueError as e:
    print("全失败 → 抛出:", e)
