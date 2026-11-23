from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from kb_service.repositories.models import User
from kb_service.repositories.rows import UserCredentialsRow, UserRow


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, user_id: UUID) -> UserRow | None:
        obj = self.session.get(User, user_id)  # 主键查，最短路径
        return obj.to_row() if obj else None

    def get_by_email(self, email: str) -> UserRow | None:
        obj = self.session.scalar(select(User).where(User.email == email))
        return obj.to_row() if obj else None

    def create(self, email: str, password_hash: str) -> UserRow:
        obj = User(email=email, password_hash=password_hash)
        self.session.add(obj)
        self.session.flush()  # commit 是 service 层的事（D3 生效）
        return obj.to_row()

    def get_credentials_by_email(self, email: str) -> UserCredentialsRow | None:
        obj = self.session.scalar(select(User).where(User.email == email))
        return obj.to_credentials_row() if obj else None
