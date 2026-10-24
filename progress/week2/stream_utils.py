"""stream_utils —— W2-D6 阶段任务。

流式处理的三个零件：
1. read_chunks : 生成器逐块读文件（SSE 边算边发的地基）
2. paginate    : 把任意可迭代切成页（分页接口的地基）
3. Cursor      : 自己实现一个"迷你 list"（D1 迭代器协议 + D5 魔术方法合体）

全部实现完后跑验收器：
    .venv\\Scripts\\python.exe ..\\progress\\week2\\check_stream_utils.py
"""

from collections.abc import Iterable, Iterator
from typing import TypeVar

T = TypeVar("T")


def read_chunks(path: str, chunk_size: int = 1024) -> Iterator[str]:
    """① 逐块读取文本文件（生成器）。

    要求：
    - 用 with open(...) 打开，保证文件一定被关闭
    - 每次 yield 最多 chunk_size 个字符
    - 读完自动停止（生成器自然结束）
    - 禁止 f.read() 不带参数——整个文件进内存正是本函数要消灭的事

    提示：f.read(chunk_size) 每次读一块，返回空字符串 "" 说明读完了。
    """
    with open(path, encoding="utf-8") as f:
        while True:
            chunk = f.read(chunk_size)
            if chunk:
                yield chunk
            else:
                break



def paginate(items: Iterable[T], page_size: int) -> Iterator[list[T]]:
    """② 把任意可迭代对象切成一页页（生成器）。

    要求：
    - items 可能是无限生成器 → 禁止 list(items)、禁止 len(items)
    - 每页最多 page_size 个元素
    - 最后一页可以不满，但元素必须一个不丢

    提示：内层循环攒一页，攒满或取完就 yield 出去。
    """
    it = iter(items)
    while True:
        result: list[T] = []
        for _ in range(page_size):
            try:
                result.append(next(it))
            except StopIteration:
                break

        if result:
            yield result
        else:
            break


class Cursor:
    """③ 迷你 list：同时是 Iterable 和 Iterator。

    关键设计：__iter__ 返回一个【全新的 Cursor】（从 0 开始），
    而不是 self——所以它可以被 for 任意多次。
    想想 D1 的实验：list 为什么能反复遍历？就是这个原理。
    """

    def __init__(self, items: Iterable[T]) -> None:
        self._items: list[T] = list(items)
        self._pos = 0

    def __iter__(self) -> "Cursor":
        """返回一个从 0 开始的新 Cursor（不是 self）。"""
        return Cursor(self._items)

    def __next__(self) -> T:
        """返回 _pos 处的元素并前移；走完 raise StopIteration。"""
        if self._pos >= len(self._items):
            raise StopIteration
        value = self._items[self._pos]
        self._pos += 1
        return value

    def __len__(self) -> int:
        """元素总数。"""
        return len(self._items)

    def __getitem__(self, index: int) -> T:
        """按下标取元素（直接转发给 _items 即可）。"""
        return self._items[index]

    def __repr__(self) -> str:
        """格式：Cursor(items=3, pos=0)"""
        return f"Cursor(items={self.__len__()}, pos={self._pos})"

    def __eq__(self, other: object) -> bool:
        """与另一个 Cursor 比较全部元素；不同类型返回 NotImplemented。"""
        if not isinstance(other, Cursor):
            return NotImplemented
        return self._items == other._items
