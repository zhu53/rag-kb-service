"""Q3 证据：asyncio 并发下 threading.local 会串号，ContextVar 不会。

跑法（在 kb-service 目录）：
    .venv/Scripts/python.exe ../progress/week1/day7_evidence/exp_local_vs_contextvar.py

预期输出：
    threading.local 串号 9/10      ← 10 个协程落在同一个线程里，共用一份 local
    ContextVar      串号 0/10      ← 每个协程有自己的上下文副本
"""

import asyncio
import threading
from contextvars import ContextVar

local = threading.local()
ctx: ContextVar[str] = ContextVar("ctx", default="<unset>")

TASKS = 10
GAP = 0.001


async def task_local(i: int) -> tuple[str, str]:
    """写入 threading.local，让出控制权后再读回来。"""
    uid = f"u{i}"
    local.uid = uid
    await asyncio.sleep(GAP)  # 这里切走，别的协程会覆盖同一个 local.uid
    return uid, getattr(local, "uid", "<unset>")


async def task_ctx(i: int) -> tuple[str, str]:
    """写入 ContextVar，让出控制权后再读回来。"""
    uid = f"u{i}"
    ctx.set(uid)
    await asyncio.sleep(GAP)
    return uid, ctx.get()


async def main() -> None:
    results = await asyncio.gather(*(task_local(i) for i in range(TASKS)))
    bad = sum(1 for expect, got in results if expect != got)
    print(f"threading.local 串号 {bad}/{TASKS}")
    for expect, got in results[:3]:
        print(f"  期望 {expect} 实际 {got}")

    results = await asyncio.gather(*(task_ctx(i) for i in range(TASKS)))
    bad = sum(1 for expect, got in results if expect != got)
    print(f"ContextVar      串号 {bad}/{TASKS}")

    print(f"线程数 {threading.active_count()}，当前线程 {threading.current_thread().name}")


if __name__ == "__main__":
    asyncio.run(main())
