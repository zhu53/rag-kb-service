"""check_json_log.py —— 任务 B 验收器（B1 + B2 的契约检查）

跑法：
    cd progress\\week1\\day6_copy
    ..\\..\\..\\kb-service\\.venv\\Scripts\\python.exe check_json_log.py

为什么需要它：B1/B2 的正确性有四项肉眼看不出来——
  1. set_trace_id 有没有把 Token 漏掉（`ALL OK` 式假绿）
  2. time 到底来自"事件发生时刻"还是"格式化时刻"
  3. trace_id 是不是真的跟着上下文走
  4. `if __name__` 那行有没有混进不可见字符
"""

from __future__ import annotations

import ast
import inspect
import json
import logging
import sys
import typing
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "json_log.py"

if sys.version_info[:2] != (3, 11):
    print(f"⚠️  当前 Python {sys.version_info[0]}.{sys.version_info[1]}，"
          "项目锁定 3.11。请用 kb-service\\.venv\\Scripts\\python.exe 跑。")
    print()

results: list[tuple[str, str, str]] = []  # (状态, 标题, 补充说明)


def check(label: str):
    def deco(fn):
        try:
            note = fn()
            results.append(("PASS", label, note or ""))
        except AssertionError as exc:
            results.append(("FAIL", label, str(exc) or "断言失败"))
        except Exception as exc:  # 验收器就是要抓所有异常，否则一项崩了后面全看不见
            results.append(("FAIL", label, f"{type(exc).__name__}: {exc}"))
        return fn

    return deco


# ---------- 0. 源码层：不可见字符 ----------
@check("0. `__main__` 守卫字符串无 HTML 实体残留")
def _() -> str:
    src = SRC.read_text(encoding="utf-8")
    tree = ast.parse(src)
    bad = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and ("&#" in node.value or "\u200b" in node.value)
    ]
    assert not bad, f"字符串常量里混进了不可见字符/实体：{bad!r}"
    return "AST 扫过所有字符串常量"


# ---------- 导入 ----------
sys.path.insert(0, str(HERE))
try:
    import json_log as m
except Exception:
    import traceback

    print("[FAIL] 模块导入失败，后面检查无法进行")
    traceback.print_exc()
    sys.exit(1)

fmt = m.JsonFormatter()


def make_record(msg: str = "测试消息", *, created: float | None = None,
                exc_info=None, **extra) -> logging.LogRecord:
    rec = logging.LogRecord("demo", logging.INFO, "x.py", 1, msg, None, exc_info)
    if created is not None:
        rec.created = created
    for k, v in extra.items():
        setattr(rec, k, v)
    return rec


# ---------- B1 ----------
@check("1. set_trace_id() 返回 Token（能被 reset）")
def _() -> str:
    m.trace_id_ctx.set("-")  # 先归零，避免上一项残留
    token = m.set_trace_id("tk-test")
    try:
        assert token is not None, (
            "返回了 None —— `trace_id_ctx.set()` 的返回值被丢掉了。"
            "B4 里 reset 需要它，会报 TypeError: expected an instance of Token, got None"
        )
        assert type(token).__name__ == "Token", (
            f"返回的是 {type(token).__name__}，不是 Token"
        )
        assert m.trace_id_ctx.get() == "tk-test"
    finally:
        # 无论断言是否失败，都要把上下文还回去，否则后面每一项都被污染
        if token is not None:
            m.trace_id_ctx.reset(token)
    assert m.trace_id_ctx.get() == "-", "reset 后没回到 set 之前的值"
    return "set → Token → reset 闭环成立"


@check("2. get_trace_id() 默认值是 '-'")
def _() -> str:
    m.trace_id_ctx.set("-")
    assert m.trace_id_ctx.get() == "-", f"默认值是 {m.trace_id_ctx.get()!r}"
    assert m.get_trace_id() == "-", f"get_trace_id() 返回 {m.get_trace_id()!r}"
    return "未被 set 时读到 '-'"


# ---------- B2 ----------
@check("3. format() 返回单行合法 JSON")
def _() -> str:
    out = fmt.format(make_record())
    assert "\n" not in out, "输出里有换行，不是单行 JSON（下游按行解析会断）"
    data = json.loads(out)
    for key in ("time", "trace_id", "level", "message"):
        assert key in data, f"JSON 里缺 {key!r} 字段，实际键 = {list(data)}"
    return f"键 = {list(data)}"


@check("4. time 来自 record.created，不是 datetime.now()")
def _() -> str:
    # 造一条 2023-11-14T22:13:20Z 发生的日志，现在才格式化
    out = fmt.format(make_record("过去的日志", created=1_700_000_000.0))
    stamp = json.loads(out)["time"]
    expected = datetime.fromtimestamp(1_700_000_000.0, UTC).isoformat()
    assert stamp == expected, (
        f"time = {stamp}，但 record.created 对应 {expected}。\n"
        "     说明用的是 datetime.now(UTC)（格式化执行的时刻），"
        "而不是 record.created（事件发生的时刻）。\n"
        "     真实后果：日志进队列/批量写出/重放时，时间会全部变成写出时刻。"
    )
    return "与 record.created 严格一致"


@check("5. trace_id 跟着上下文变，不是常量")
def _() -> str:
    rec = make_record("上下文测试")
    token = m.set_trace_id("aaa")
    try:
        a = json.loads(fmt.format(rec))["trace_id"]
    finally:
        m.trace_id_ctx.reset(token)
    token = m.set_trace_id("bbb")
    try:
        b = json.loads(fmt.format(rec))["trace_id"]
    finally:
        m.trace_id_ctx.reset(token)
    assert a == "aaa", f"上下文为 aaa 时读到 {a!r}"
    assert b == "bbb", f"上下文为 bbb 时读到 {b!r}"
    return "同一 record 在不同上下文下 trace_id 不同"


@check("6. 中文不转义（ensure_ascii=False）")
def _() -> str:
    out = fmt.format(make_record("用户 张三 登录失败"))
    assert "\\u" not in out, "中文被转成 \\uXXXX 了，缺 ensure_ascii=False"
    assert "张三" in out
    return "可直接人读"


@check("7. 真实异常能带出 traceback")
def _() -> str:
    try:
        raise ValueError("模拟炸了")
    except ValueError:
        rec = make_record("出错了", exc_info=sys.exc_info())
    data = json.loads(fmt.format(rec))
    assert "exception" in data, "有 exc_info 却没输出 exception 字段"
    assert "ValueError: 模拟炸了" in data["exception"]
    assert "Traceback" in data["exception"]
    return "exception 字段含完整堆栈"


@check("8. exc_info=(None,None,None) 不产生 'NoneType: None' 垃圾")
def _() -> str:
    rec = make_record("空异常", exc_info=(None, None, None))
    data = json.loads(fmt.format(rec))
    dumped = json.dumps(data, ensure_ascii=False)
    assert "NoneType: None" not in dumped, (
        "输出了 'NoneType: None'。"
        "这是 exc_info=True 在 except 块外被调用时的产物，"
        "半个判断 `record.exc_info[0] is not None` 就是挡这个的。"
    )
    return "空异常被正确忽略"


@check("9. 所有类型注解可求值（import 没漏）")
def _() -> str:
    bad: list[str] = []
    for name, obj in vars(m).items():
        if getattr(obj, "__module__", None) != m.__name__:
            continue
        if inspect.isfunction(obj):
            targets = [(name, obj)]
        elif inspect.isclass(obj):
            targets = [
                (f"{name}.{mname}", meth)
                for mname, meth in inspect.getmembers(obj, inspect.isfunction)
            ]
        else:
            continue
        for label, fn in targets:
            try:
                typing.get_type_hints(fn)
            except NameError as exc:
                bad.append(f"{label} -> {exc}")
    assert not bad, (
        "以下函数/方法的注解求值失败（运行时**完全不报错**，"
        "因为 `from __future__ import annotations` 把注解变成了永不求值的字符串）：\n     "
        + "\n     ".join(bad)
    )
    return "get_type_hints() 全部通过"


# ---------- 软提示 ----------
def warn() -> list[str]:
    notes = []
    rec = make_record("带自定义字段", path="/api/v1/kbs/stats/count")
    data = json.loads(fmt.format(rec))
    if "path" not in data:
        notes.append(
            "WARN  extra 自定义字段（path 等）没有进入 JSON。\n"
            "      你现在用的是白名单（只挑 time/trace_id/level/message），\n"
            "      白名单天然免疫'保留字段混入'，代价是每条自定义字段都要显式加一行。\n"
            "      B4 要记录 path，届时用 getattr(record, 'path', None) 取。"
        )
    return notes


def pending_steps(src: str) -> list[str]:
    """找出还是 `...` / `pass` 空壳的函数（按 AST 判断，不靠字符串搜索）。"""

    def is_stub(body: list[ast.stmt]) -> bool:
        for stmt in body:
            if isinstance(stmt, ast.Pass):
                continue
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                if stmt.value.value is Ellipsis:
                    continue
                if isinstance(stmt.value.value, str):  # docstring
                    continue
            return False
        return True

    tree = ast.parse(src)
    bodies = {
        node.name: node.body
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    steps = [("B3 setup_logging", "setup_logging"),
             ("B4 handle_request", "handle_request"),
             ("B5 main", "main")]
    out = []
    for label, name in steps:
        body = bodies.get(name)
        if body is None or is_stub(body):
            out.append(label)
    return out


warnings = warn()

# ---------- 输出 ----------
print()
if results:
    width = max(len(r[1]) for r in results)
    for status, label, note in results:
        mark = "✅" if status == "PASS" else "❌"
        print(f"{mark} {status:4}  {label}")
        if note:
            for line in note.splitlines():
                print(f"          {line}")
    print()

passed = sum(1 for s, _, _ in results if s == "PASS")
total = len(results)
print(f"{passed} / {total} 通过 —— B1 + B2")

for w in warnings:
    print()
    print(w)

todo = pending_steps(SRC.read_text(encoding="utf-8"))

if todo:
    print()
    print("待写：" + "、".join(todo))

if passed < total:
    print()
    print("还没到收工。逐条改，改一条跑一次。")
    sys.exit(1)
print()
print("B1 + B2 契约全过。可以进 B3 了。")
