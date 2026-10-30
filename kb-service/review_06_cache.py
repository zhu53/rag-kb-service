"""会话 TTL 缓存：为 /chat 复用检索上下文（W14 换成 Redis 实现）。

自检：python review_06_cache.py [测试名 ...]
"""

from __future__ import annotations

import asyncio
import sys
import time
from typing import Any

DEFAULT_TTL = 60.0


class TTLCache:
    """极简异步 TTL 缓存。

    put/get 做成协程是为了保留异步边界：真实实现（W14 的 Redis 版）
    要 await 网络往返，调用方代码届时无需改写。
    """

    def __init__(self) -> None:
        self._data: dict[str, tuple[Any, float]] = {}

    async def put(self, key: str, value: Any, ttl: float = DEFAULT_TTL) -> None:
        """写入值并记录过期时刻。"""
        await asyncio.sleep(0)
        self._data[key] = (value, time.time() + ttl)

    async def get(self, key: str) -> Any | None:
        """读取值；已过期则顺手淘汰并返回 None。"""
        await asyncio.sleep(0)
        item = self._data.get(key)
        if item is None:
            return None
        value, deadline = item
        if time.time() >= deadline:
            self._data.pop(key, None)
            return None
        return value

    async def warm_up(self, pairs: dict[str, Any], ttl: float = DEFAULT_TTL) -> int:
        """批量预热，返回写入条数。"""
        for key, value in pairs.items():
            await self.put(key, value, ttl)
        return len(pairs)


cache = TTLCache()


# ---------------------------- 自检 ----------------------------


async def test_put_then_get() -> None:
    await cache.put("session:1", "hello")
    assert await cache.get("session:1") == "hello"


async def test_reuse_from_earlier_session() -> None:
    """同一会话再次进入时应能取回上一轮写入的上下文。"""
    assert await cache.get("session:1") == "hello"


async def test_missing_key_returns_none() -> None:
    assert await cache.get("session:missing") is None


async def test_expired_key_returns_none() -> None:
    await cache.put("session:ttl", "gone", ttl=0.05)
    await asyncio.sleep(0.15)
    assert await cache.get("session:ttl") is None


async def test_warm_up_saves_new_keys() -> None:
    cache.put("bulk:keep", "manual", ttl=30)
    count = await cache.warm_up({"bulk:keep": "bulk", "bulk:new": 2}, ttl=30)
    assert count == 2
    assert await cache.get("bulk:new") == 2


TESTS = [
    test_put_then_get,
    test_reuse_from_earlier_session,
    test_missing_key_returns_none,
    test_expired_key_returns_none,
    test_warm_up_saves_new_keys,
]


def main() -> int:
    """跑全部自检；带参数时只跑指定名字的用例。"""
    selected = TESTS
    if len(sys.argv) > 1:
        wanted = set(sys.argv[1:])
        selected = [t for t in TESTS if t.__name__ in wanted]
        if not selected:
            print(f"没有匹配的测试：{sorted(wanted)}")
            return 2

    failed = 0
    for test in selected:
        try:
            asyncio.run(test())
        except AssertionError:
            failed += 1
            print(f"FAIL {test.__name__}")
        else:
            print(f"PASS {test.__name__}")

    print(f"\n{len(selected) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
