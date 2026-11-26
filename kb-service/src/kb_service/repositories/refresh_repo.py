from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.orm import Session

from kb_service.repositories.models import RefreshToken


class RefreshTokenRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        """四步拒绝链的第 1 步：把 hash 当查询键，一步查行。"""
        return self.session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )

    def rotate(self, old: RefreshToken, new_hash: str, expires_at: datetime) -> None:
        """同事务轮换：revoke 旧行 + insert 新行。commit 是 service 的事，这里只 flush/add。"""
        old.revoked_at = datetime.now(UTC)
        self.session.add(
            RefreshToken(user_id=old.user_id, token_hash=new_hash, expires_at=expires_at)
        )

    def revoke_by_hash(self, token_hash: str) -> bool:
        """把票标成 revoked，返回是否真的改到了行（幂等：重复退出返回 False 不报错）。"""
        row = self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == token_hash, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        return cast(CursorResult[Any], row).rowcount > 0
