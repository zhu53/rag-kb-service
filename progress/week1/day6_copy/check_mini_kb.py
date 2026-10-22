"""check_mini_kb.py —— 任务 A 的自动验收器（8 项）

用法（必须用项目 3.11 跑）：
    cd progress\week1\day6_copy
    ..\..\..\kb-service\.venv\Scripts\python.exe check_mini_kb.py

它只检查"你的 mini_kb.py 是否满足 8 条性质"，不告诉你答案怎么写。
哪条 FAIL 就回去改哪条，改完再跑，直到 8/8 PASS。

为什么需要它：
    `python mini_kb.py` 打印 ALL OK **不代表对**。
    2026-10-22 实测：Windows + Python 3.11 的 datetime.now() 精度只有 15.6ms，
    两次 create() 拿到同一时间戳 → list.sort 退化成插入顺序 →
    items[1] 那条断言"绿得毫无意义"。自测通过 ≠ 逻辑正确。
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import get_type_hints
from uuid import UUID, uuid4

# ---------------- 环境守卫 ----------------
if sys.version_info >= (3, 12):
    major, minor = sys.version_info[:2]
    print(f"⚠️  你正在用 Python {major}.{minor} 跑这个验收器。")
    print("    项目锁定的是 3.11，时钟精度差异会让结论失真。")
    print("    请改用：..\\..\\..\\kb-service\\.venv\\Scripts\\python.exe check_mini_kb.py")
    sys.exit(2)
else:
    print(f"Python {sys.version.split()[0]}  ✓ 与项目环境一致\n")

sys.path.insert(0, str(Path(__file__).resolve().parent))

# 默认验收 mini_kb.py；想拿参考实现对照就跑 check_mini_kb.py mini_kb_reference
MODULE = sys.argv[1] if len(sys.argv) > 1 else "mini_kb"
if MODULE.endswith(".py"):
    MODULE = MODULE[:-3]

try:
    import importlib

    m = importlib.import_module(MODULE)
    print(f"被验收的模块：{MODULE}.py\n")
except Exception:
    print(f"[FAIL] 0. 模块 {MODULE} 导入失败，后面 7 项无法检查")
    traceback.print_exc()
    sys.exit(1)

results: list[tuple[str, str]] = []


def check(label: str):
    """装饰器：把一条检查包成 PASS/FAIL 记录。"""

    def wrap(fn):
        try:
            detail = fn()
            results.append(("PASS", f"{label}{('  —— ' + detail) if detail else ''}"))
        except Exception as exc:
            msg = str(exc) or type(exc).__name__
            results.append(("FAIL", f"{label}  —— {msg}"))
        return fn

    return wrap


svc = None
try:
    svc = m.KBService()  # 缺 = None 时这里直接 TypeError
except TypeError as exc:
    results.append(("FAIL", f"1. KBService() 能无参构造  —— {exc}"))
    svc = m.KBService(None)  # 降级，让后面 7 项还能检查
else:
    results.append(("PASS", "1. KBService() 能无参构造  —— 说明 __init__ 的 repo 有默认值"))

me, other = uuid4(), uuid4()


@check("2. store.now() 严格递增（时间戳不撞车）")
def _():
    t1 = svc.create(me, "时钟-1").created_at
    t2 = svc.create(me, "时钟-2").created_at
    assert t1 != t2, (
        "两次 create 拿到同一时间戳 → 排序会退化成插入顺序（在 3.11 下几乎必然发生）"
    )
    assert t2 > t1, f"时间没有递增：{t1} → {t2}"
    return "单调兜底生效"


@check("3. list() 真的按创建时间倒序")
def _():
    svc.create(me, "排序-A")
    svc.create(me, "排序-B")  # 后创建
    items, _total = svc.list(me, page=1, size=100)
    names = [it.name for it in items]
    i_a, i_b = names.index("排序-A"), names.index("排序-B")
    assert i_b < i_a, (
        f"「排序-B」（后创建）在第 {i_b} 位，「排序-A」在第 {i_a} 位 —— 后创建的应该更靠前"
    )
    return "后创建的在前"


@check("4. list() 只返回自己的，且 total 为切片前总数")
def _():
    _before, n_before = svc.list(me, page=1, size=100)
    svc.create(other, "别人的-1")
    svc.create(other, "别人的-2")
    after, n_after = svc.list(me, page=1, size=100)
    assert n_after == n_before, f"别人的库混进了我的计数：{n_before} → {n_after}"
    assert all(it.owner_id == me for it in after), "返回了别人的库"
    page1, total = svc.list(me, page=1, size=1)
    assert total == n_after, f"total 应该是总数 {n_after}，实际 {total}（是不是切完片才数的？）"
    assert len(page1) == 1, f"size=1 却返回 {len(page1)} 条，分页没生效"
    return f"共 {total} 条，size=1 只返 1 条"


@check("5. KBOut 的类型注解可求值（拼写正确）")
def _():
    hints = get_type_hints(m.KBOut.from_row)
    assert "return" in hints, "from_row 没有返回注解"
    get_type_hints(m.KBService.list)
    return f"from_row 返回 {hints['return'].__name__}"


@check("6. 数据行的 id 是 UUID 实例，不是 str")
def _():
    row = svc.repo.create(me, "id-类型测试")
    assert isinstance(row["id"], UUID), (
        f"id 是 {type(row['id']).__name__}，不是 UUID（是不是 str(uuid4()) 了？）"
    )
    return "key 与 value 类型一致"


@check("7. to_dict() 能直接 json.dumps（任务 C 的前提）")
def _():
    kb = svc.create(me, "序列化测试")
    d = kb.to_dict()
    # 契约 2026-10-22 晚升级：FastAPI 实测证明 dict[str, str] 太窄——
    # doc_count 应为 int（否则前端 "0"+1 得 "01"）。新契约：值必须 JSON 可序列化。
    json_safe = (str, int, float, bool, type(None))
    bad = {k: type(v).__name__ for k, v in d.items() if not isinstance(v, json_safe)}
    assert not bad, f"这些字段无法 JSON 序列化，JSONResponse 会炸 TypeError：{bad}"
    assert isinstance(d["doc_count"], int), (
        f"doc_count 是 {type(d['doc_count']).__name__}，应为 int（前端拿到 '0' 做加法会得到 '01'）"
    )
    json.dumps(d)
    return "全部字段 JSON 可序列化，doc_count 是 int"


@check("8. 权限语义：不存在→NotFound，别人的→Forbidden")
def _():
    kb = svc.create(me, "权限测试")
    try:
        svc.get_or_403(uuid4(), me)
        raise AssertionError("不存在的 id 没有抛异常")
    except m.NotFoundError:
        pass
    try:
        svc.get_or_403(kb.id, other)
        raise AssertionError("访问别人的库没有抛异常")
    except m.ForbiddenError:
        pass
    svc.delete(kb.id, me)
    try:
        svc.get_or_403(kb.id, me)
        raise AssertionError("删除后仍能查到")
    except m.NotFoundError:
        pass
    return "404 先于 403，删除后不可见"


# ---------------- 汇总 ----------------
print("=" * 66)
for status, text in results:
    mark = "✅ PASS" if status == "PASS" else "❌ FAIL"
    print(f"{mark}  {text}")
print("=" * 66)

passed = sum(1 for s, _ in results if s == "PASS")
total_n = len(results)
print(f"\n{passed} / {total_n} 通过")

if passed == total_n:
    print("\n任务 A 验收通过。可以提交了。")
    sys.exit(0)
else:
    print("\n还没到收工。逐条改，改一条跑一次这个脚本。")
    print("提示：ruff 能顺手清掉注解拼写和格式问题 ——")
    print("      cd ../../../kb-service")
    print("      uv run ruff check --fix ../progress/week1/day6_copy/mini_kb.py")
    sys.exit(1)
