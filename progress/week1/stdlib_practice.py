"""W1 Day4-Day5 · 标准库默写练习（12 道）

用法：
    1. 先合上答案，自己写 TODO 部分
    2. 写完后运行：python stdlib_practice.py
    3. 全部打印 [PASS] 才算完成本周 Day4-Day5

要求：
    - 每个函数都要有类型注解（Day5 会用 mypy strict 检查）
    - 不许 import 题目没提到的模块之外的第三方库
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from itertools import chain, zip_longest
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Protocol

# ---------------------------------------------------------------- Day4


def ex01_list_py_files(root: Path) -> list[tuple[str, int]]:
    """遍历 root 下所有 .py 文件，返回 [(路径, 字节数)]，按大小降序。

    练习点：pathlib.Path.rglob / stat().st_size / sorted(key=)
    """
    result: list[tuple[str, int]] = []
    for p in root.rglob("*.py"):
        if p.is_file():
            result.append((str(p), p.stat().st_size))
    return sorted(result, key=lambda x: x[1], reverse=True)


def ex02_make_json_safe(obj: object) -> str:
    """把 datetime 对象序列化成 ISO 字符串（json.dumps 的 default 参数）。

    练习点：json.dumps(default=...)
    """

    def default(o: object) -> str:
        if isinstance(o, datetime):
            return o.isoformat()
        raise TypeError(f"不可序列化的类型：{type(o).__name__}")

    return json.dumps(obj, default=default)


@dataclass(frozen=True, slots=True)
class DbConfig:
    host: str
    port: int = 5432
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """构造时校验：port 必须在 1-65535 之间，否则 raise ValueError。"""
        if not 1 <= self.port <= 65535:
            raise ValueError(f"port 必须在 1-65535 之间，当前值 {self.port}")


def ex03_top_words(text: str, n: int = 10) -> list[tuple[str, int]]:
    """统计词频 Top-N。

    练习点：re.findall / Counter.most_common
    """
    if not text:
        return []
    words = re.findall(r"[a-z']+", text.lower())
    return Counter(words).most_common(n)


_MISSING = object()


def ex04_merge_alternating(a: list[str], b: list[str]) -> list[str]:
    """[a1,a2],[b1,b2] -> [a1,b1,a2,b2]，长度不等时多余部分直接接在后面。

    练习点：itertools.zip_longest / chain
    """
    pairs = zip_longest(a, b, fillvalue=_MISSING)
    return [v for v in chain.from_iterable(pairs) if v is not _MISSING]


def ex05_rotating_logger(log_dir: Path) -> object:
    """返回一个写入了 RotatingFileHandler 的 logger，单文件 1MB、保留 3 个。

    练习点：logging.getLogger / RotatingFileHandler / Formatter
    """
    logger = logging.getLogger("stdlib_practice")
    handler = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=1 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


def ex06_sliding_max(values: list[int], k: int) -> list[int]:
    """滑动窗口最大值 —— 必须用 deque，不许用 max(slice)。

    练习点：collections.deque（单调队列，O(n)）
    例：[1,3,-1,-3,5,3,6,7], k=3 -> [3,3,5,5,6,7]
    """
    dq: deque[int] = deque()  # 存下标，对应值从队头到队尾递减
    result: list[int] = []
    for i, v in enumerate(values):
        while dq and values[dq[-1]] <= v:
            dq.pop()
        dq.append(i)
        if dq[0] <= i - k:
            dq.popleft()
        if i >= k - 1:
            result.append(values[dq[0]])
    return result


# ---------------------------------------------------------------- Day5


class Storable(Protocol):
    """结构化子类型：只要实现了 to_dict() 就算可存储。"""

    def to_dict(self) -> dict[str, str]: ...


class UserDoc:
    def __init__(self, name: str) -> None:
        self.name = name

    def to_dict(self) -> dict[str, str]:
        return {"type": "user", "name": self.name}


class NoteDoc:
    def __init__(self, title: str) -> None:
        self.title = title

    def to_dict(self) -> dict[str, str]:
        return {"type": "note", "title": self.title}


def ex07_flush_all(docs: list[Storable]) -> None:
    """把一批 Storable 对象落盘（这里只做打印）。

    练习点：Protocol 让两个毫无继承关系的类都能传进来，且 mypy 认账。
    """
    # TODO: 你的实现
    raise NotImplementedError("ex07")


async def ex08_fetch_all(urls: list[str], concurrency: int = 3) -> list[str]:
    """并发"请求"一批 URL，限制最大并发数。

    这里用 asyncio.sleep 模拟 IO。要求：返回顺序与输入一致。
    练习点：asyncio.Semaphore / TaskGroup / 收集结果顺序
    """
    # TODO: 你的实现
    raise NotImplementedError("ex08")


def ex09_cli_parser() -> object:
    """构造一个 argparse parser：支持 --verbose 开关、--count 整数、--mode {fast,slow}。

    练习点：argparse.ArgumentParser.add_argument 的 action/type/choices
    """
    # TODO: 你的实现
    raise NotImplementedError("ex09")


@contextlib.contextmanager
def ex10_timer(label: str = "elapsed"):
    """计时上下文管理器，退出时打印 label 与耗时毫秒。

    练习点：contextlib.contextmanager / try-finally
    """
    # TODO: 你的实现
    raise NotImplementedError("ex10")


def ex11_fib_cached(n: int) -> int:
    """带缓存的斐波那契，要求同时能打印缓存命中情况。

    练习点：functools.lru_cache / cache_info()
    """
    # TODO: 你的实现
    raise NotImplementedError("ex11")


class DocStatus(StrEnum):
    """用 StrEnum 定义文档状态（已经是正确写法，照抄理解即可）。"""

    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


def ex12_group_by_status(rows: list[dict[str, str]]) -> dict[DocStatus, list[str]]:
    """把 [{"id": "1", "status": "ready"}, ...] 按状态分组。

    练习点：defaultdict + StrEnum 的成员查找
    """
    # TODO: 你的实现
    raise NotImplementedError("ex12")


# ---------------------------------------------------------------- 自检器


def _check_no(name: str, fn, expectation) -> None:  # type: ignore[no-untyped-def]
    try:
        got = fn()
    except NotImplementedError:
        print(f"[TODO] {name} 还没实现")
        return
    except Exception as exc:
        print(f"[FAIL] {name} 抛出异常：{type(exc).__name__}: {exc}")
        return
    if expectation(got):
        print(f"[PASS] {name}")
    else:
        print(f"[FAIL] {name} 结果不符：{got!r}")


def _run_selfcheck() -> None:
    tmp = Path(__file__).parent / "_tmp"
    tmp.mkdir(exist_ok=True)
    (tmp / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp / "b.py").write_text("y = 2\n" * 50, encoding="utf-8")

    _check_no("ex01", lambda: ex01_list_py_files(tmp), lambda r: len(r) == 2 and r[0][1] > r[1][1])
    _check_no(
        "ex02",
        lambda: ex02_make_json_safe({"t": datetime(2026, 10, 20, tzinfo=UTC)}),
        lambda r: "2026-10-20" in r,
    )
    _check_no("ex03", lambda: ex03_top_words("a b a c a b", 2), lambda r: r[0] == ("a", 3))

    def _ex04() -> list[str]:
        return ex04_merge_alternating(["a1", "a2", "a3"], ["b1"])

    _check_no("ex04", _ex04, lambda r: r == ["a1", "b1", "a2", "a3"])
    _check_no("ex05", lambda: ex05_logger_ok(), lambda r: r is True)
    _check_no("ex06", lambda: ex06_sliding_max([1, 3, -1, -3, 5, 3, 6, 7], 3),
              lambda r: r == [3, 3, 5, 5, 6, 7])

    def _ex07() -> None:
        ex07_flush_all([UserDoc("qi"), NoteDoc("w1")])

    _check_no("ex07", lambda: _ex07() or True, lambda r: r is True)

    async def _ex08_wrap() -> list[str]:
        return await ex08_fetch_all([f"u{i}" for i in range(5)], concurrency=2)

    _check_no("ex08", lambda: asyncio.run(_ex08_wrap()), lambda r: r[0] == "u0" and len(r) == 5)

    def _ex09() -> object:
        return ex09_cli_parser().parse_args(["--count", "3", "--mode", "fast"])

    _check_no("ex09", _ex09, lambda r: r.count == 3 and r.mode == "fast")  # type: ignore[attr-defined]

    def _ex10() -> float:
        start = time.perf_counter()
        with ex10_timer("check"):
            time.sleep(0.01)
        return time.perf_counter() - start

    _check_no("ex10", _ex10, lambda r: r >= 0.01)
    _check_no("ex11", lambda: (ex11_fib_cached(10), ex11_fib_cached(10))[0], lambda r: r == 55)
    _check_no(
        "ex12",
        lambda: ex12_group_by_status([{"id": "1", "status": "ready"},
                                      {"id": "2", "status": "ready"},
                                      {"id": "3", "status": "pending"}]),
        lambda r: len(r[DocStatus.READY]) == 2,
    )


def ex05_logger_ok() -> bool:
    """ex05 的辅助校验：能返回带 handler 的 logger。"""
    logger = ex05_rotating_logger(Path(__file__).parent / "_tmp")
    return hasattr(logger, "handlers") and len(logger.handlers) > 0  # type: ignore[union-attr]


if __name__ == "__main__":
    _run_selfcheck()
