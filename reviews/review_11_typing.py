"""文档视图装配：给列表接口和归档模块复用。

只做内存过滤，不碰数据库——从 store 取出来的行已经是 dict 形态。
"""

from __future__ import annotations

from typing import Any, cast

SAMPLE_ROWS: list[dict[str, Any]] = [
    {"id": "d-1", "title": "RAG 入门", "chunk_count": 3},
    {"id": "d-2", "title": "向量检索", "chunk_count": 7},
    {"id": "d-3", "title": "重排与召回", "chunk_count": 12},
]


class DocView:
    """在一个文档集合上做查询与摘要。"""

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows if rows is not None else list(SAMPLE_ROWS)

    def find(self, doc_id: object) -> dict[str, Any]:
        """按 id 查找文档，找不到时返回空 dict。"""
        target = str(doc_id)
        for row in self._rows:
            if str(row.get("id")) == target:
                return row
        return {}

    def first_title(self) -> Any:
        """第一篇文章的标题；没有数据时返回空串。"""
        if not self._rows:
            return ""
        return self._rows[0]["title"]

    def summary(self, doc_id: object) -> str:
        """拼一句「标题: 分块数」的摘要。"""
        row = cast(dict[str, Any], self.find(doc_id) or None)
        return f"{row['title']}: {row['chunk_count']} 块"

    def titles(self) -> list[str]:
        """所有标题，用于列表接口的首屏字段。"""
        out: list[str] = []
        for row in self._rows:
            title = row.get("title")
            if isinstance(title, str):
                out.append(title)
        return out


def main() -> None:
    """手工验一遍主链路。"""
    view = DocView()
    print("标题列表:", view.titles())
    print("第一篇:", view.first_title())
    print("摘要 d-2:", view.summary("d-2"))
    print("查 d-99 的结果:", view.find("d-99"))


if __name__ == "__main__":
    main()
