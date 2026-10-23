from typing import Iterator, Iterable, TypeVar

def read_lines(path: str) -> Iterator[str]:
    with open(path, encoding="utf-8") as f:
        for line in f:
            yield line.strip("\n")

def lib() -> Iterator[int]:
    a, b = 0, 1
    while True:
        yield a
        a, b = b, a + b

def take(iterable: Iterable[T], n: int) -> Iterator[T]:
    count = 0
    for item in iterable:
        if count >= n:
            break
        yield item
        count += 1
