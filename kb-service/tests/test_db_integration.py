r"""真 MySQL 集成测试：只回答一个问题——**commit 有没有真的发生**。

和 `tests/` 其他用例的分工：

| | 其他用例 | 本文件 |
|---|---|---|
| 介质 | sqlite 内存库 | 真 MySQL 8.4 |
| 目的 | 业务逻辑对不对（快、可隔离） | 事务边界对不对（慢、但真） |
| 能测出 | 分页、鉴权、切块、序列化 | **commit 漏了 / flush 当 commit 用** |
| 测不出 | MySQL 方言（TEXT 默认值、FK 索引覆盖、gap lock） | — |

为什么 `KBRepository.list_by_owner` 在 sqlite 上过了这里还要再验：
sqlite 的默认隔离级别和行为跟 InnoDB 不同，而且 sqlite 单文件没有"另一个连接"
这个概念上的独立性——**只有真库才能证明"提交了别的会话才看得见"**。

为什么不建独立 `kb_test` 库（原计划）：
`kb` 账号没有 CREATE 权限（实测 1044 Access denied）。
折中方案：用 `kb_dev` + 专属 owner UUID 隔离——断言只查自己这个 owner，
结束按 owner 删干净，不清表、不碰别人的行。
（面试可讲：没有 DBA 授权时，测试隔离靠"数据归属"而不是"库归属"。）

跑法（PowerShell，kb-service 目录下）：

    $env:KB_TEST_MYSQL="1"
    & .\.venv\Scripts\python.exe -m pytest tests\test_db_integration.py -q

不设这个变量就整体 skip，`check.py` 门禁不受影响。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import UUID

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from kb_service.core.config import get_settings
from kb_service.repositories.doc_repo import DocRepository
from kb_service.repositories.kb_repo import KBRepository
from kb_service.schemas.doc import DocCreate
from kb_service.schemas.kb import KBCreate
from kb_service.services.doc_service import DocService
from kb_service.services.kb_service import KBService

pytestmark = pytest.mark.skipif(
    os.environ.get("KB_TEST_MYSQL") != "1",
    reason="需要真 MySQL：设 $env:KB_TEST_MYSQL=1 后再跑",
)

# 专属 owner：不和探针（8888…/9999…）、单元测试（1111…/2222…）撞
OWNER = UUID("77777777-7777-4777-8777-777777777777")

engine = create_engine(get_settings().database_url)
maker = sessionmaker(bind=engine, expire_on_commit=False)


def _purge() -> None:
    """只删本文件造的数据；DB 级 FK CASCADE 会带走 documents / chunks。"""
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM knowledge_bases WHERE owner_id = :o"), {"o": OWNER.hex})


@pytest.fixture(autouse=True)
def clean() -> Iterator[None]:
    _purge()
    yield
    _purge()


def test_kb_create_commits_and_other_session_sees_it() -> None:
    """KB 建库：service 的 commit 一旦漏掉，另一个会话就看不到。

    这条用例就是"删掉一句 commit → 必须红"的那个变异体的检测器。
    """
    s1 = maker()
    try:
        KBService(KBRepository(s1), session=s1).create(OWNER, KBCreate(name="集成-库A"))
    finally:
        s1.close()  # 只关闭、不 commit：落库只能靠 service 里那一次

    s2 = maker()
    try:
        rows, total = KBRepository(s2).list_by_owner(OWNER, 0, 10)
        assert total == 1, (
            f"另一个会话看不到这行（total={total}）——service 里的 commit 是不是被删了？"
        )
        assert rows[0]["name"] == "集成-库A"
    finally:
        s2.close()


def test_document_chunks_and_counter_commit_together() -> None:
    """传文档：正文 / chunks / status / doc_count 必须在同一次 commit 里落地。

    任何一项对不上，说明这一步没进那个事务（或者被拆成了两次 commit，
    那就失去了原子性——中途失败会留下"文档在、块不在"的半成品）。
    """
    body = "测试文档内容" * 200  # 1200 字 → chunk_size=400 / overlap=50 → 4 块
    kb_id: UUID

    s1 = maker()
    try:
        kb_id = KBService(KBRepository(s1), session=s1).create(OWNER, KBCreate(name="集成-库B")).id
        DocService(DocRepository(s1), session=s1, kb_repo=KBRepository(s1)).create(
            kb_id, OWNER, DocCreate(title="集成-文档", content=body)
        )
    finally:
        s1.close()

    s2 = maker()
    try:
        doc = (
            s2.execute(
                text(
                    "SELECT CHAR_LENGTH(content) AS clen, status, chunk_count "
                    "FROM documents WHERE kb_id = :kb"
                ),
                {"kb": kb_id.hex},
            )
            .mappings()
            .one()
        )
        chunk_rows = s2.execute(
            text(
                "SELECT COUNT(*) FROM chunks c "
                "JOIN documents d ON c.doc_id = d.id WHERE d.kb_id = :kb"
            ),
            {"kb": kb_id.hex},
        ).scalar()
        doc_count = s2.execute(
            text("SELECT doc_count FROM knowledge_bases WHERE id = :kb"),
            {"kb": kb_id.hex},
        ).scalar()
    finally:
        s2.close()

    assert doc["clen"] == 1200, "正文没落库（models.py 的 to_row / create 里 content 没传？）"
    assert doc["status"] == "ready", "status 没推进到 ready"
    assert doc["chunk_count"] == 4
    assert chunk_rows == 4, "chunks 表没写（_parse_sync 没调 add_chunks？）"
    assert doc_count == 1, "doc_count 没自增（incr_doc_count 没在事务里？）"
