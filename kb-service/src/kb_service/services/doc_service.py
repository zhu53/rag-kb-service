from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from kb_service.core.exceptions import NotFoundError
from kb_service.repositories.doc_repo import DocRepository
from kb_service.repositories.kb_repo import KBRepository
from kb_service.repositories.protocols import DocRepo, KBRepo
from kb_service.repositories.rows import DocRow
from kb_service.schemas.doc import DocCreate, DocOut
from kb_service.schemas.kb import Page
from kb_service.services.kb_service import KBService


class DocService:
    def __init__(
        self,
        repo: DocRepo | None = None,
        session: Session | None = None,
        kb_repo: KBRepo | None = None,
    ) -> None:
        # "repo 与 session 至少给一个"——这个检查不是防御性编程的洁癖：
        # 漏传的后果是 session=None 一路往下传，最后在调用处才炸，
        # 报错点离病因隔了三层。在入口炸，堆栈第一行就是答案。
        if repo is None:
            if session is None:
                raise ValueError("DocService 需要 repo 或 session 之一")
            repo = DocRepository(session)
        if kb_repo is None:
            if session is None:
                raise ValueError("DocService 需要 kb_repo 或 session 之一")
            kb_repo = KBRepository(session)
        self._session = session
        self.repo = repo
        self.kb_service = KBService(kb_repo, session=session)

    def _commit(self) -> None:
        """一次业务动作 = 一次 commit"""
        if self._session is None:
            return
        self._session.commit()

    def create(self, kb_id: UUID, user_id: UUID, data: DocCreate) -> DocOut:
        self.kb_service.get_or_403(kb_id, user_id)
        row = self.repo.create(kb_id, data)
        self.kb_service.repo.incr_doc_count(kb_id, 1)

        # W11 TODO：这里改成 submit_parse_task.delay(doc_id)，把同步解析改成异步。
        n = self._parse_sync(row)
        self._commit()
        fresh: DocRow = {**row, "status": "ready", "chunk_count": n}
        return DocOut.model_validate(fresh)

    def list(self, kb_id: UUID, user_id: UUID, page: int, size: int) -> Page[DocOut]:
        self.kb_service.get_or_403(kb_id, user_id)
        offset = (page - 1) * size
        rows, total = self.repo.list_by_kb(kb_id, offset, size)
        return Page[DocOut](
            items=[DocOut.model_validate(r) for r in rows],
            total=total,
            page=page,
            size=size,
        )

    def get(self, doc_id: UUID, user_id: UUID) -> DocOut:
        row = self.repo.get(doc_id)
        if row is None:
            raise NotFoundError("文档不存在")
        self.kb_service.get_or_403(row["kb_id"], user_id)
        return DocOut.model_validate(row)

    def delete(self, doc_id: UUID, user_id: UUID) -> None:
        row = self.repo.get(doc_id)
        if row is None:
            raise NotFoundError("文档不存在")
        self.kb_service.get_or_403(row["kb_id"], user_id)
        self.repo.delete(doc_id)
        self.kb_service.repo.incr_doc_count(row["kb_id"], -1)
        self._commit()

    def _parse_sync(self, row: DocRow) -> int:
        """同步解析：切块 → 写 chunks 表 → 标 ready。返回切块数。"""
        text: str = row["content"]
        pieces = split_text(text, chunk_size=400, overlap=50)
        self.repo.add_chunks(row["id"], pieces)  # ← 新增这行
        self.repo.update_status(row["id"], "ready", chunk_count=len(pieces))
        return len(pieces)  # ← 返回切块数


def split_text(text: str, *, chunk_size: int = 400, overlap: int = 50) -> list[str]:
    """按字符窗口切分（简单版）。

    W12 TODO：升级为按段落/句子边界切分，并实现父子块（parent-child chunking）。
    overlap 保证跨块语义不被切断；assert 防止踩到无限循环。
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size 必须大于 0")
    if overlap >= chunk_size:
        raise ValueError("overlap 必须小于 chunk_size")

    step = chunk_size - overlap
    chunks: list[str] = []
    for start in range(0, len(text), step):
        chunk = text[start : start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
        if start + chunk_size >= len(text):
            break
    return chunks
