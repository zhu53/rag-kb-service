"""D5 任务 2：模拟索引后台任务的最小测试。"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from kb_service.services.indexing import run_index


def test_run_index_happy_path() -> None:
    """正常路径不抛异常即通过；真实断言由文档状态在集成层体现。"""
    asyncio.run(run_index(uuid4(), "测试内容"))
