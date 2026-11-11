"""模拟索引后台任务（D5 任务 2 教学版）。

W12 TODO：换成真实的切块 + embedding + 向量库写入，仍以后台任务形式挂载。
"""

from __future__ import annotations

import logging
import time
from uuid import UUID

logger = logging.getLogger("kb_service.indexing")


def run_index(doc_id: UUID, content: str) -> None:
    """模拟索引一篇文档：真实场景是切块 + embedding + 写向量库（W12 替换）。"""
    try:
        logger.info("索引开始 doc_id=%s content_len=%s", doc_id, len(content))
        time.sleep(0.3)  # 模拟 embedding / 写库的耗时（真实场景 embedding SDK 是同步客户端）
        logger.info("索引完成 doc_id=%s", doc_id)
    except Exception:
        logger.exception("索引失败 doc_id=%s", doc_id)
