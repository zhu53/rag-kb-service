"""exp_trace_id.py —— 全局变量 vs ContextVar 的并发对照实验

这是**观察实验**，不是今天的作业。先跑，看懂输出，再写 json_log.py。

跑法：
    cd progress\week1\day6_copy
    ..\..\..\kb-service\.venv\Scripts\python.exe exp_trace_id.py

它模拟的是：10 个请求同时进来，每个请求一进门就记下自己的 trace_id，
中间 await 一下（等价于查数据库、调模型），然后再打日志。
问题：**打日志那一刻，读到的还是自己那个 trace_id 吗？**
"""

from __future__ import annotations

import asyncio
import random
from contextvars import ContextVar

# ---------------------------------------------------------------
# 方案 1：全局变量。全进程只有一份，谁最后写谁说了算
# ---------------------------------------------------------------
_current_global: str = "-"


async def work_global(trace_id: str) -> tuple[str, str]:
    global _current_global
    _current_global = trace_id  # 进门记下自己的身份
    await asyncio.sleep(random.uniform(0, 0.01))  # 模拟 IO 等待（关键！）
    return trace_id, _current_global  # 打日志时读回来


# ---------------------------------------------------------------
# 方案 2：ContextVar。每个 asyncio task 各自持有一份
# ---------------------------------------------------------------
trace_id_ctx: ContextVar[str] = ContextVar("trace_id", default="-")


async def work_contextvar(trace_id: str) -> tuple[str, str]:
    trace_id_ctx.set(trace_id)  # 只影响当前这条执行流
    await asyncio.sleep(random.uniform(0, 0.01))
    return trace_id, trace_id_ctx.get()


async def run_batch(worker, label: str) -> int:
    """并发跑 10 个请求，返回"串号"的次数。"""
    n = 10
    results = await asyncio.gather(*(worker(f"t-{i}") for i in range(n)))
    bad = 0
    print(f"\n=== {label} ===")
    for expect, actual in results:
        ok = expect == actual
        bad += not ok
        print(f"  请求 {expect:>3}  →  读到的 trace_id = {actual:<4}  {'✓' if ok else '✗ 串了'}")
    print(f"  ---- 串号 {bad} / {n} ----")
    return bad


async def main() -> None:
    print("场景：10 个请求同时进来，每个先 set 自己的 trace_id，await 一下，再读回来打日志。")
    bad_global = await run_batch(work_global, "方案 1：全局变量 _current_global")
    bad_ctx = await run_batch(work_contextvar, "方案 2：ContextVar trace_id_ctx")

    print("\n" + "=" * 60)
    print(f"全局变量串号：{bad_global} 次")
    print(f"ContextVar 串号：{bad_ctx} 次")
    print("=" * 60)
    print("\n结论：全局变量是'一人写，全楼看'——最后写的那个把别人的覆盖了。")
    print("      ContextVar 是'每人一份，跟着执行流走'——asyncio task / 线程 各自独立。")
    print("\n注意 await 那一行：没有它，每个请求都是'set 完立刻读'，看起来也不会串。")
    print("真实服务里一定有 IO 等待，串号问题才会暴露出来。")


if __name__ == "__main__":
    asyncio.run(main())
