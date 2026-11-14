from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from kb_service.repositories.rows import DocRow, KBRow


class Base(DeclarativeBase):
    pass


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    doc_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    docs: Mapped[list[Document]] = relationship(back_populates="kb", cascade="all, delete-orphan")

    def to_row(self) -> KBRow:
        return KBRow(
            id=self.id,
            owner_id=self.owner_id,
            name=self.name,
            description=self.description,
            doc_count=self.doc_count,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    kb_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    chunk_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    kb: Mapped[KnowledgeBase] = relationship(back_populates="docs")
    chunks: Mapped[list[Chunk]] = relationship(back_populates="doc", cascade="all, delete-orphan")

    def to_row(self) -> DocRow:
        return DocRow(
            id=self.id,
            kb_id=self.kb_id,
            title=self.title,
            content="",
            status=self.status,
            chunk_count=self.chunk_count,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    doc_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column()  # 分块在文档里的顺序号
    content: Mapped[str] = mapped_column(Text)  # 分块正文
    doc: Mapped[Document] = relationship(back_populates="chunks")
