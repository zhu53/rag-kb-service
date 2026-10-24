class Doc:
    def __init__(self, doc_id: str, content: str):
        self.doc_id = doc_id
        self.content = content

    # ① __repr__：打印成 Doc(id='xxx', chars=N) 的样子
    def __repr__(self):
        return f"Doc(id = {self.doc_id!r}, char = {len(self.content)})"

    # ② __eq__：按 doc_id 判断相等；不同类型返回 NotImplemented
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Doc):
            return NotImplemented
        return self.doc_id == other.doc_id

    # ③ @property char_count：返回 len(content)

    @property
    def char_count(self):
        return len(self.content)


if __name__ == "__main__":
    doc = Doc("doc_id", "content")
    other = Doc("doc_id", "other content")
    print(doc == other)
    print(doc)
    print(doc.char_count)
    print(Doc("a", "x") == "a")
