from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kb_service.repositories.models import Chunk, Document
from kb_service.repositories.rows import DocRow
from kb_service.schemas.doc import DocCreate


class DocRepository:
    """文档数据访问层。W7 TODO：换成 SQLAlchemy。"""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, kb_id: UUID, data: DocCreate, *, status: str = "pending") -> DocRow:
        obj = Document(
            kb_id=kb_id,
            title=data.title,
            status=status,
            content=data.content,
        )
        self.session.add(obj)
        self.session.flush()
        return obj.to_row()

    def get(self, doc_id: UUID) -> DocRow | None:
        obj = self.session.get(Document, doc_id)
        return obj.to_row() if obj else None

    def list_by_kb(self, kb_id: UUID, offset: int, limit: int) -> tuple[list[DocRow], int]:
        page = self.session.scalars(
            select(Document)
            .where(Document.kb_id == kb_id)
            .order_by(Document.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        total = self.session.scalar(
            select(func.count()).select_from(Document).where(Document.kb_id == kb_id)
        )
        return [d.to_row() for d in page], total or 0

    def delete(self, doc_id: UUID) -> bool:
        obj = self.session.get(Document, doc_id)
        if obj is None:
            return False
        self.session.delete(obj)
        return True

    def update_status(self, doc_id: UUID, status: str, chunk_count: int | None = None) -> None:
        obj = self.session.get(Document, doc_id)
        if obj is None:
            return
        obj.status = status
        if chunk_count is not None:
            obj.chunk_count = chunk_count

    def add_chunks(self, doc_id: UUID, texts: list[str]) -> None:
        self.session.add_all([Chunk(doc_id=doc_id, seq=i, content=t) for i, t in enumerate(texts)])
        self.session.flush()
