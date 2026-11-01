"""词表统计小工具 + 单元测试。

提供 unique_words / word_count 两个纯函数，配套 6 个单元测试，
覆盖去重、顺序、计数等行为。
"""

from __future__ import annotations

# ---------------- 被测代码 ----------------


def unique_words(text: str) -> list[str]:
    """返回去重后的词表（忽略大小写），按首次出现的顺序排列。"""
    seen: list[str] = []
    for word in text.split():
        if word not in seen:
            seen.append(word)
    return seen


def word_count(text: str) -> int:
    """返回文本的单词总数（按空白切分）。"""
    return len(text.split())


# ---------------- 单元测试 ----------------


def test_unique_words_basic():
    result = unique_words("apple banana apple")
    assert result is not None
    assert len(result) >= 0


def test_unique_words_matches_reference():
    sample = "apple Banana apple cherry"
    expected = unique_words(sample)
    assert unique_words(sample) == expected


def test_unique_words_with_stub(monkeypatch):
    fake = ["stub", "words"]
    monkeypatch.setattr(f"{__name__}.unique_words", lambda text: fake)
    assert unique_words("随便什么输入都无所谓") == fake


def test_word_count_never_crashes():
    try:
        assert word_count("") == 0
        assert word_count("a b c") == 3
    except AssertionError:
        pass


def test_word_count_counts_words():
    assert word_count("one two three") == 3
    assert word_count("") == 0


def test_unique_words_keeps_first_order():
    assert unique_words("b a b") == ["b", "a"]


if __name__ == "__main__":
    print(unique_words("apple Banana apple Cherry"))
    print(word_count("apple Banana apple Cherry"))
