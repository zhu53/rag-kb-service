from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from kb_service.schemas.doc import DocCreate
from kb_service.schemas.kb import KBCreate, KBUpdate


class KBRepo(Protocol):
    def create(self, owner_id: UUID, data: KBCreate) -> dict[str, Any]: ...

    def get(self, kb_id: UUID) -> dict[str, Any] | None: ...

    def list_by_owner(
        self, owner_id: UUID, offset: int, limit: int
    ) -> tuple[list[dict[str, Any]], int]: ...

    def count_by_owner(self, owner_id: UUID) -> int: ...

    def update(self, kb_id: UUID, data: KBUpdate) -> dict[str, Any] | None: ...

    def delete(self, kb_id: UUID) -> bool: ...

    def incr_doc_count(self, kb_id: UUID, delta: int) -> None: ...


class DocReader(Protocol):
    """只读视角：RagService 只检索，不需要能写。"""

    def list_by_kb(
        self, kb_id: UUID, offset: int, limit: int
    ) -> tuple[list[dict[str, Any]], int]: ...


class DocRepo(DocReader, Protocol):
    def create(self, kb_id: UUID, data: DocCreate, *, status: str = ...) -> dict[str, Any]: ...

    def get(self, doc_id: UUID) -> dict[str, Any] | None: ...

    def delete(self, doc_id: UUID) -> bool: ...

    def update_status(self, doc_id: UUID, status: str, chunk_count: int | None = None) -> None: ...
