"""check_stream_utils —— W2-D6 验收器（10 项）。

运行方式（在 kb-service 目录下）：
    .venv\\Scripts\\python.exe ..\\progress\\week2\\check_stream_utils.py

判分：每项 1 分。10 = 满分；6 及以下回炉对应条目。
"""

from itertools import islice
from pathlib import Path
from tempfile import mkdtemp

import stream_utils as su

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, fn) -> None:
    try:
        detail = fn() or ""
        RESULTS.append((name, True, detail))
    except Exception as exc:
        RESULTS.append((name, False, f"{type(exc).__name__}: {exc}"))


def _tmpfile(content: str) -> Path:
    p = Path(mkdtemp()) / "sample.txt"
    p.write_text(content, encoding="utf-8")
    return p


# ---------- read_chunks（4 项） ----------


def t1_is_generator() -> str:
    p = _tmpfile("abc")
    g = su.read_chunks(str(p), 2)
    assert hasattr(g, "__next__"), "返回对象没有 __next__，不是生成器"
    return "type=" + type(g).__name__


def t2_content_intact() -> str:
    p = _tmpfile("abcdefghij")
    joined = "".join(su.read_chunks(str(p), 4))
    assert joined == "abcdefghij", f"拼回来变成 {joined!r}"
    return "拼接完整"


def t3_chunk_size_respected() -> str:
    p = _tmpfile("abcdefghij")
    chunks = list(su.read_chunks(str(p), 4))
    assert all(len(c) <= 4 for c in chunks), f"有块超长: {chunks}"
    assert chunks[0] == "abcd", f"第一块应为 'abcd'，实际 {chunks[0]!r}"
    return f"{len(chunks)} 块: {chunks}"


def t4_empty_file() -> str:
    p = _tmpfile("")
    chunks = list(su.read_chunks(str(p), 4))
    assert chunks == [], f"空文件应产出 0 块，实际 {chunks}"
    return "空文件 0 块"


# ---------- paginate（3 项） ----------


def t5_basic_pages() -> str:
    pages = list(su.paginate(range(10), 3))
    expect = [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9]]
    assert pages == expect, f"实际 {pages}"
    return "10 个元素 → 4 页"


def t6_infinite_generator() -> str:
    def fib():
        a, b = 0, 1
        while True:
            yield a
            a, b = b, a + b

    pages = list(islice(su.paginate(fib(), 4), 2))
    expect = [[0, 1, 1, 2], [3, 5, 8, 13]]
    assert pages == expect, f"实际 {pages}"
    return "无限生成器只取前 2 页，没卡死"


def t7_empty_input() -> str:
    pages = list(su.paginate([], 3))
    assert pages == [], f"空输入应产出 0 页，实际 {pages}"
    return "空输入 0 页"


# ---------- Cursor（3 项） ----------


def t8_reusable_iteration() -> str:
    c = su.Cursor([1, 2, 3])
    first = [x for x in c]
    second = [x for x in c]
    assert first == [1, 2, 3], f"第一次遍历 {first}"
    assert second == [1, 2, 3], f"第二次遍历 {second} —— 是不是把 self 返回了？"
    return "两次 for 都拿到全部元素（可复用）"


def t9_len_getitem_repr() -> str:
    c = su.Cursor(["a", "b", "c"])
    assert len(c) == 3, f"len 应为 3，实际 {len(c)}"
    assert c[1] == "b", f"c[1] 应为 'b'，实际 {c[1]!r}"
    r = repr(c)
    assert "Cursor" in r, f"repr 应含 Cursor，实际 {r!r}"
    assert "3" in r, f"repr 应含元素数，实际 {r!r}"
    return f"len=3, c[1]='b', repr={r!r}"


def t10_eq_safe() -> str:
    c = su.Cursor([1, 2, 3])
    assert c == su.Cursor([1, 2, 3]), "相同元素应相等"
    assert c != su.Cursor([1, 2]), "不同元素应不等"
    assert (c == "not a cursor") is False, "与 str 比较应返回 False 而不是炸"
    return "eq 三连通过"


check("1  read_chunks 返回的是生成器", t1_is_generator)
check("2  read_chunks 内容一个不丢", t2_content_intact)
check("3  read_chunks 块大小不超标", t3_chunk_size_respected)
check("4  read_chunks 空文件产出 0 块", t4_empty_file)
check("5  paginate 基本切页", t5_basic_pages)
check("6  paginate 能处理无限生成器", t6_infinite_generator)
check("7  paginate 空输入", t7_empty_input)
check("8  Cursor 可反复遍历", t8_reusable_iteration)
check("9  Cursor len/getitem/repr", t9_len_getitem_repr)
check("10 Cursor eq 三连（含类型守卫）", t10_eq_safe)

print()
passed = 0
for name, ok, detail in RESULTS:
    mark = "✅" if ok else "❌"
    passed += ok
    print(f"{mark} {name}")
    if detail:
        print(f"     {detail}")

print(f"\n总分: {passed} / 10", "🎉 满分！" if passed == 10 else "")
