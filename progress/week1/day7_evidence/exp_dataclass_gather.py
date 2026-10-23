"""Q5 / Q7 证据：dataclass 可变默认值 fail-fast，gather 孤儿 vs TaskGroup 取消。

跑法（在 kb-service 目录）：
    .venv/Scripts/python.exe ../progress/week1/day7_evidence/exp_dataclass_gather.py

预期输出：
    Q5 类定义时就抛：ValueError: mutable default <class 'list'>
        for field items is not allowed: use default_factory
    Q7 gather 抛给调用方：boom
    Q7 gather 抛异常瞬间，slow 完成了吗？没有（done=[]）
    Q7 gather 0.2s 后：done=['gather-slow']  ← 没被取消，孤儿跑完了
    Q7 TaskGroup 抛 ExceptionGroup，内含 1 个：(RuntimeError('boom'),)
    Q7 TaskGroup 0.2s 后：done=[]  ← 被取消，没跑完
"""

import asyncio
from dataclasses import dataclass

DONE: list[str] = []


def show_dataclass_error() -> None:
    """不写 default_factory 时，类定义那一刻就抛 ValueError。"""
    try:

        @dataclass
        class Bad:
            items: list = []  # noqa: RUF008 —— 故意演示错误写法

    except Exception as exc:
        print(f"Q5 类定义时就抛：{type(exc).__name__}: {exc}")


async def boom() -> None:
    """10ms 后失败。"""
    await asyncio.sleep(0.01)
    raise RuntimeError("boom")


async def slow(name: str) -> None:
    """150ms 后完成。"""
    await asyncio.sleep(0.15)
    DONE.append(name)


async def demo_gather() -> None:
    """gather：异常抛给调用方，其余协程不取消，继续跑成孤儿。"""
    try:
        await asyncio.gather(boom(), slow("gather-slow"))
    except RuntimeError as exc:
        print(f"Q7 gather 抛给调用方：{exc}")
    print(f"Q7 gather 抛异常瞬间，slow 完成了吗？{'是' if DONE else '没有'}（done={DONE}）")
    await asyncio.sleep(0.2)
    print(f"Q7 gather 0.2s 后：done={DONE}  ← 没被取消，孤儿跑完了")


async def demo_taskgroup() -> None:
    """TaskGroup：一个失败，其余全部取消，抛 ExceptionGroup。"""
    DONE.clear()
    try:
        async with asyncio.TaskGroup() as group:
            group.create_task(boom())
            group.create_task(slow("tg-slow"))
    except* RuntimeError as group_exc:
        detail = f"内含 {len(group_exc.exceptions)} 个：{group_exc.exceptions}"
        print(f"Q7 TaskGroup 抛 ExceptionGroup，{detail}")
    await asyncio.sleep(0.2)
    print(f"Q7 TaskGroup 0.2s 后：done={DONE}  ← 被取消，没跑完")


def main() -> None:
    show_dataclass_error()
    asyncio.run(demo_gather())
    asyncio.run(demo_taskgroup())


if __name__ == "__main__":
    main()
