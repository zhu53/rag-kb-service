from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from kb_service.schemas.common import not_blank

DocTitle = Annotated[str, Field(min_length=1, max_length=200), AfterValidator(not_blank)]
DocContent = Annotated[str, Field(min_length=1, max_length=20000), AfterValidator(not_blank)]


class DocStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class DocCreate(BaseModel):
    title: DocTitle
    content: DocContent


class DocOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kb_id: UUID
    title: str
    status: DocStatus
    chunk_count: int
    created_at: datetime
    updated_at: datetime
