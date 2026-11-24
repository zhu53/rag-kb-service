from sqlalchemy.orm import Session

from kb_service.core.exceptions import UnauthorizedError
from kb_service.core.security import create_access_token, hash_password, verify_password
from kb_service.repositories.rows import UserRow
from kb_service.repositories.user_repo import UserRepository
from kb_service.schemas.auth import LoginIn, RegisterIn

_DUMMY_HASH = hash_password("fake password")


class AuthService:
    def __init__(self, repo: UserRepository, session: Session) -> None:
        self._repo = repo
        self._session = session

    def _commit(self) -> None:
        self._session.commit()

    def register(self, data: RegisterIn) -> UserRow:
        email = data.email.strip().lower()
        row = self._repo.create(email, hash_password(data.password))
        self._commit()
        return row
        # 重复 email 不在这里 try：交给全局 IntegrityError handler → 409

    def login(self, data: LoginIn) -> str:
        email = data.email.strip().lower()
        row = self._repo.get_credentials_by_email(email)
        if row is None:
            verify_password(data.password, _DUMMY_HASH)
            raise UnauthorizedError("邮箱或密码错误")
        if not verify_password(data.password, row["password_hash"]):
            raise UnauthorizedError("邮箱或密码错误")
        if row["is_banned"]:
            raise UnauthorizedError("邮箱或密码错误")
        return create_access_token(str(row["id"]))
