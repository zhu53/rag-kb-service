from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from kb_service.core.config import get_settings
from kb_service.core.exceptions import UnauthorizedError
from kb_service.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    refresh_token_hash,
    verify_password,
)
from kb_service.repositories.models import RefreshToken
from kb_service.repositories.refresh_repo import RefreshTokenRepository
from kb_service.repositories.rows import UserRow
from kb_service.repositories.user_repo import UserRepository
from kb_service.schemas.auth import LoginIn, RefreshIn, RegisterIn

_DUMMY_HASH = hash_password("fake password")


class AuthService:
    def __init__(self, repo: UserRepository, session: Session) -> None:
        self._repo = repo
        self._session = session
        self._refresh_repo = RefreshTokenRepository(session)

    def _commit(self) -> None:
        self._session.commit()

    def register(self, data: RegisterIn) -> UserRow:
        email = data.email.strip().lower()
        row = self._repo.create(email, hash_password(data.password))
        self._commit()
        return row
        # 重复 email 不在这里 try：交给全局 IntegrityError handler → 409

    def login(self, data: LoginIn) -> tuple[str, str]:
        email = data.email.strip().lower()
        row = self._repo.get_credentials_by_email(email)
        if row is None:
            verify_password(data.password, _DUMMY_HASH)
            raise UnauthorizedError("邮箱或密码错误")
        if not verify_password(data.password, row["password_hash"]):
            raise UnauthorizedError("邮箱或密码错误")
        if row["is_banned"]:
            raise UnauthorizedError("邮箱或密码错误")
        access = create_access_token(str(row["id"]))
        refresh = self.create_refresh_token(row["id"])
        self._commit()
        return access, refresh

    def create_refresh_token(self, user_id: UUID) -> str:
        raw = generate_refresh_token()
        settings = get_settings()
        row = RefreshToken(
            user_id=user_id,
            token_hash=refresh_token_hash(raw),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
        )
        self._session.add(row)
        return raw

    def refresh(self, data: RefreshIn) -> tuple[str, str]:
        presented = refresh_token_hash(data.refresh_token)
        row = self._refresh_repo.get_by_hash(presented)

        if row is None:
            raise UnauthorizedError("用户凭证无效")
        if row.revoked_at is not None:
            raise UnauthorizedError("用户凭证无效")
        # MySQL DATETIME 不存时区，读回来是 naive；写入时一律按 UTC 存，
        # 所以这里把它当作 UTC 补上时区标记，再和 aware 的 now 比。
        expires_at = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            raise UnauthorizedError("用户凭证无效")
        user = self._repo.get(row.user_id)
        if user is None or user["is_banned"]:
            raise UnauthorizedError("用户凭证无效")

        new_raw = generate_refresh_token()
        self._refresh_repo.rotate(
            row,
            refresh_token_hash(new_raw),
            datetime.now(UTC) + timedelta(days=get_settings().refresh_token_expire_days),
        )
        self._commit()
        return create_access_token(str(user["id"])), new_raw

    def logout(self, data: RefreshIn) -> None:
        self._refresh_repo.revoke_by_hash(refresh_token_hash(data.refresh_token))
        self._commit()
        # 不 raise：票不存在/已撤销也都算成功——幂等，且不泄漏"这张票是否存在"
