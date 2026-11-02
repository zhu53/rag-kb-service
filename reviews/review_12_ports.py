"""文档端口 / 适配器骨架。

报告服务只依赖 `DocumentPort` 声明的能力，不认具体存储；
测试环境用 `StubDocuments` 顶替，旧版代码走 `LegacyDocuments` 适配。

直接运行可看到一份示例报告：

    python reviews/review_12_ports.py
"""

from __future__ import annotations

from typing import Any, Protocol, cast, runtime_checkable
from uuid import UUID, uuid4

Row = dict[str, Any]


@runtime_checkable
class DocumentPort(Protocol):
    """报告服务需要的仓库能力。"""

    def find(self, doc_id: UUID) -> Row | None: ...

    def all(self) -> list[Row]: ...


@runtime_checkable
class SnapshotPort(Protocol):
    """可整体导出的仓库。"""

    def load(self) -> object: ...


class MemoryDocuments:
    """真实实现：内存字典，key 用完整 UUID。"""

    def __init__(self) -> None:
        self._rows: dict[UUID, Row] = {}

    def add(self, title: str, body: str) -> UUID:
        doc_id = uuid4()
        self._rows[doc_id] = {"id": doc_id, "title": title, "body": body}
        return doc_id

    def find(self, doc_id: UUID) -> Row | None:
        return self._rows.get(doc_id)

    def all(self) -> list[Row]:
        return list(self._rows.values())

    def load(self) -> list[Row]:
        return list(self._rows.values())


class StubDocuments:
    """测试替身：用固定样本代替存储，不碰真实数据。"""

    def __init__(self, rows: list[Row]) -> None:
        self._rows = rows

    def find(self, doc_id: str) -> Row | None:
        for row in self._rows:
            if row["id"] == doc_id:
                return row
        return None

    def all(self) -> list[Row]:
        return list(self._rows)


class LegacyDocuments:
    """旧版存储的适配器：从 v0 代码直接搬过来的，改动最小。"""

    def __init__(self) -> None:
        self._rows: dict[str, Row] = {}

    def load(self) -> object:
        return list(self._rows.values())

    def find(self, key: str) -> Row | None:
        return self._rows.get(key)

    def all(self) -> list[Row]:
        return list(self._rows.values())


class Reporter:
    """统计一批文档的命中情况。"""

    def __init__(self, docs: DocumentPort) -> None:
        self.docs = docs

    def summarize(self, ids: list[UUID]) -> str:
        found = 0
        missing = 0
        for doc_id in ids:
            row = self.docs.find(doc_id) or {}
            if row.get("title"):
                found += 1
            else:
                missing += 1
        return f"命中 {found} 篇，缺失 {missing} 篇"


class Exporter:
    """把仓库里所有行拼成一行文本。"""

    def __init__(self, snap: SnapshotPort) -> None:
        self.snap = snap

    def export(self) -> str:
        payload = cast("list[Row]", self.snap.load())
        titles = [str(r.get("title", "?")) for r in payload]
        return "导出：" + "、".join(titles)


def describe(docs: object) -> str:
    """按能力判断：像文档仓库就报明细，否则只报不支持。"""
    if isinstance(docs, DocumentPort):
        return f"端口兼容，共 {len(docs.all())} 篇"
    return "不支持文档端口"


def _sample_rows() -> list[Row]:
    return [
        {"id": "d-1", "title": "分层", "body": "api 只做翻译"},
        {"id": "d-2", "title": "事务", "body": "边界放 service"},
        {"id": "d-3", "title": "并发", "body": "锁要够小"},
    ]


def main() -> None:
    real = MemoryDocuments()
    ids = [
        real.add("分层", "api 只做翻译"),
        real.add("事务", "边界放 service"),
        real.add("并发", "锁要够小"),
    ]
    print("真实现：", Reporter(real).summarize(ids))

    stub = StubDocuments(_sample_rows())
    print("测试替身：", Reporter(stub).summarize(ids))  # type: ignore[arg-type]

    legacy = LegacyDocuments()
    print("旧版适配：", describe(legacy))
    print("旧版 isinstance：", isinstance(legacy, DocumentPort))

    print("快照导出：", Exporter(real).export())


if __name__ == "__main__":
    main()
