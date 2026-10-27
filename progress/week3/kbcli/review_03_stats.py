"""词频统计小工具：带命中统计的缓存包装。

供 kbcli 的 `stats` 子命令（规划中）使用：把"查词"包一层缓存，
并统计命中率，方便判断缓存容量是否给小了。
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any


class StatsCache:
    """带命中率统计的 LRU 缓存（默认容量 3，演示用）。"""

    def __init__(self, capacity: int = 3) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be > 0")
        self.capacity = capacity
        self._data: OrderedDict[str, Any] = OrderedDict()
        self._total = 0
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Any:
        """查词：命中计数 +1，未命中计数 +1 并返回 None。"""
        if key in self._data:
            self.hits += 1
            return self._data[key]
        self.misses += 1
        return None

    def put(self, key: str, value: Any) -> None:
        """写入词条，容量溢出时淘汰最旧的一条。"""
        if key not in self._data:
            self._total += 1
        self._data[key] = value
        if len(self._data) > self.capacity:
            self._data.popitem(last=False)

    def remove(self, key: str) -> bool:
        """删除词条，返回是否真的删了。"""
        existed = key in self._data
        if existed:
            del self._data[key]
        return existed

    def rate(self) -> float:
        """缓存命中率，0~1 之间的小数。"""
        total = self.hits + self.misses
        return self.hits / total if total else 0.0


def build_report(cache: StatsCache, words: list[str]) -> list[str]:
    """把一批词的查询结果整理成人话报表，一行一条。"""
    report = []
    for word in words:
        value = cache.get(word)
        report.append(f"{word}={'<未收录>' if value is None else value}")
    report.append(f"共查询 {len(words)} 个词")
    return report


if __name__ == "__main__":
    cache = StatsCache(3)
    cache.put("fastapi", "Web 框架")
    cache.put("uv", "包管理器")
    cache.put("pydantic", "数据校验")

    print("查 fastapi →", cache.get("fastapi"))
    print("查 ruff →", cache.get("ruff"))
    cache.put("ruff", "Linter")  # 容量满，触发淘汰
    print("当前词条数:", cache._total)

    print("hits:", cache.hits, "misses:", cache.misses)
