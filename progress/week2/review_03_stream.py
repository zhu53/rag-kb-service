"""ingest 批处理的读取工具集（重构版）。

把原来散在脚本里的读取/分页逻辑收进一个模块，
供 doc_ingest 批处理脚本复用。
"""

from collections.abc import Iterable, Iterator
from itertools import islice
from pathlib import Path
from tempfile import mkdtemp
from typing import TypeVar

T = TypeVar("T")


def read_chunks(path: str, chunk_size: int = 64) -> Iterator[str]:
    """按块读取文本文件，每块最多 chunk_size 个字符。"""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    for start in range(0, len(text), chunk_size):
        yield text[start : start + chunk_size]


def paginate(items: Iterable[T], page_size: int) -> Iterator[list[T]]:
    """把任意可迭代对象切成一页页，每页 page_size 个元素。"""
    it = iter(items)
    while True:
        page: list[T] = []
        for _ in range(page_size):
            try:
                page.append(next(it))
            except Exception:
                break
        if page:
            yield page
        else:
            break


class Cursor:
    """游标：包一段数据，支持遍历、取长度和相等比较。"""

    def __init__(self, items: Iterable[T]) -> None:
        self._items: list[T] = list(items)
        self._pos = 0

    def __iter__(self) -> "Cursor":
        return self

    def __next__(self) -> T:
        if self._pos >= len(self._items):
            raise StopIteration
        value = self._items[self._pos]
        self._pos += 1
        return value

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, index: int) -> T:
        return self._items[index]

    def __repr__(self) -> str:
        return f"Cursor(items={len(self._items)}, pos={self._pos})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Cursor):
            return NotImplemented
        return self._items == other._items

    def __hash__(self):
        return hash(tuple(self._items))


if __name__ == "__main__":
    sample = Path(mkdtemp()) / "ingest.txt"
    sample.write_text("0123456789" * 5, encoding="utf-8")

    chunks = list(read_chunks(str(sample), 10))
    intact = "".join(chunks) == sample.read_text(encoding="utf-8")
    print("chunks:", chunks[:3], f"... 共 {len(chunks)} 块，拼接一致: {intact}")

    pages = list(islice(paginate((i * i for i in range(10**9)), 5), 3))
    print("pages:", pages)

    cursor = Cursor(["a", "b", "c"])
    print("first:", [x for x in cursor])
    print("len:", len(cursor), "| eq:", cursor == Cursor(["a", "b", "c"]))
