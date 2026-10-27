from collections import OrderedDict
from typing import Any


class LRUCache:
    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be > 0")
        self.capacity = capacity
        self.cache: OrderedDict[str, Any] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Any:
        if key in self.cache:
            self.cache.move_to_end(key)
            self.hits += 1
            return self.cache[key]
        self.misses += 1
        return None

    def put(self, key: str, val: Any) -> None:
        if key in self.cache:
            self.cache.move_to_end(key)

        self.cache[key] = val
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)

    def delete(self, key: str) -> None:
        self.cache.pop(key, None)

    def __len__(self) -> int:
        return len(self.cache)

    def clear(self) -> None:
        self.cache.clear()

    @property
    def hit_rate(self) -> float:
        total = self.misses + self.hits
        return self.hits / total if total > 0 else 0


if __name__ == "__main__":
    c = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    assert c.get("a") == 1  # a 变成最新
    c.put("c", 3)  # 容量溢出 → 淘汰最旧的 b
    assert c.get("b") is None
    assert len(c) == 2
    assert c.get("a") == 1  # 命中

    c.put("a", 99)
    assert c.get("a") == 99  # 覆盖写生效

    print("hit_rate:", c.hit_rate)
