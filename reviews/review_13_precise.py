"""文档索引：内存检索 + 摘要服务。

enrichment 阶段给索引行补摘要，Index 提供按 id / 按条数两种取法，
normalize_status 负责把外部状态串转成内部状态字面量。
"""

from __future__ import annotations

from typing import Literal, TypedDict, cast, overload

Status = Literal["draft", "ready", "archived"]


class IndexEntry(TypedDict):
    """检索索引里的一行。"""

    doc_id: str
    title: str
    tokens: list[str]


class EnrichedEntry(IndexEntry, total=False):
    """补过摘要的行：summary 由 enrichment 阶段写入，可能还没有。"""

    summary: str
    status: str


def make_entry(doc_id: str, title: str) -> IndexEntry:
    words = title.split()
    return {"doc_id": doc_id, "title": title, "tokens": words}


def enrich(e: IndexEntry, summary: str) -> EnrichedEntry:
    out: EnrichedEntry = {**e, "summary": summary, "status": "draft"}
    return out


def entry_line(e: EnrichedEntry) -> str:
    return f"[{e['title']}] {e['summary']}"


def summary_of(e: EnrichedEntry) -> str:
    return e.get("summary") or "(无摘要)"


def normalize_status(raw: str) -> Status:
    """把外部状态字符串转成内部状态字面量。"""
    return cast("Status", raw.strip())


class Index:
    """倒排前的线性索引：支持按 id 精确取、按条数批量取。"""

    def __init__(self) -> None:
        self._docs: dict[str, EnrichedEntry] = {}

    def add(self, e: EnrichedEntry) -> None:
        self._docs[e["doc_id"]] = e

    def all(self) -> list[EnrichedEntry]:
        return list(self._docs.values())

    def count_ready(self) -> int:
        return sum(1 for e in self._docs.values() if e.get("status") == "ready")

    @overload
    def get(self, key: str) -> list[str]: ...

    @overload
    def get(self, key: int) -> list[str]: ...

    def get(self, key: str | int) -> list[str]:
        if isinstance(key, str):
            return [e["title"] for e in self._docs.values() if e["doc_id"].startswith(key)]
        return []

    def mark_ready(self, doc_id: str, raw: str) -> None:
        row = self._docs.get(doc_id)
        if row is not None:
            row["status"] = normalize_status(raw)


def main() -> None:
    idx = Index()
    idx.add(enrich(make_entry("d-1", "分层 架构"), "api 只做翻译"))
    idx.add(enrich(make_entry("d-2", "事务 边界"), "边界放 service"))
    idx.add(enrich(make_entry("d-3", "并发 锁"), "锁要够小"))

    for e in idx.all():
        print(entry_line(e))

    print("按前缀查：", idx.get("d-"))
    print("就绪计数：", idx.count_ready())

    idx.mark_ready("d-2", "ready")
    print("标记后就绪：", idx.count_ready())

    print("状态：", normalize_status("ready"))
    print("摘要回退：", summary_of(enrich(make_entry("d-9", "缓存"), "")))


if __name__ == "__main__":
    main()
