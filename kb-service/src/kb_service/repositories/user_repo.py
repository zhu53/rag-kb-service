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

    def get_all_users(self) -> list[UserRow]:
        """admin 列表用：全量用户，按建号时间排序（稳定输出，测试不用赌行序）。"""
        objs = self.session.scalars(select(User).order_by(User.created_at)).all()
        return [obj.to_row() for obj in objs]

    def set_banned(self, user_id: UUID, banned: bool) -> UserRow | None:
        """改封禁位，返回改后的快照；用户不存在返回 None（由路由翻成 404）。

        返回快照而不是 bool：路由要把新状态回给客户端，再查一次就多一次查询。
        """
        obj = self.session.get(User, user_id)
        if obj is None:
            return None
        obj.is_banned = banned
        self.session.flush()
        return obj.to_row()
