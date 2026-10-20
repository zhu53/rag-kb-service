from __future__ import annotations

import pytest

from kb_service.services.doc_service import split_text


def test_chunk_count_normal() -> None:
    """1000 字、chunk 400 / overlap 50 → step 350，起点 0/350/700 → 3 块。"""
    assert len(split_text("x" * 1000)) == 3


def test_short_text_single_chunk() -> None:
    assert len(split_text("hello")) == 1


def test_overlap_equal_chunk_size_raises() -> None:
    """overlap == chunk_size 会让 step 变成 0，range() 直接抛 ValueError。

    回归测试：曾把校验写成 `overlap > chunk_size`，
    放过了等号，导致程序一路跑到 range() 才炸。
    """
    with pytest.raises(ValueError, match="overlap 必须小于 chunk_size"):
        split_text("x" * 1000, chunk_size=400, overlap=400)


def test_overlap_greater_than_chunk_size_raises() -> None:
    with pytest.raises(ValueError, match="overlap 必须小于 chunk_size"):
        split_text("x" * 1000, chunk_size=400, overlap=500)


def test_chunk_size_zero_raises() -> None:
    with pytest.raises(ValueError, match="chunk_size 必须大于 0"):
        split_text("x" * 1000, chunk_size=0)
