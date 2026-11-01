from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from jose import JWTError, jwt
from passlib.context import CryptContext

from kb_service.core.config import get_settings
from kb_service.core.exceptions import UnauthorizedError

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(raw: str) -> str:
    return _pwd_ctx.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    return _pwd_ctx.verify(raw, hashed)


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    """签发 JWT。subject 一般是 user_id。"""
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        **(extra or {}),
    }
    # python-jose 没有类型标注（pyproject 里 ignore_missing_imports），jwt.encode
    # 被 mypy 视为 Any。这里用 cast 声明"我知道它返回 str"：运行时 jose 确实返回 str。
    # 用 cast 而不是 str(...) 是因为 str() 会悄悄改变行为（万一返回 bytes 会被转成
    # "b'...'"），cast 是零运行时开销的纯声明，错了会在下游立刻暴露。
    return cast(str, jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm))


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload: dict[str, Any] = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
        return payload
    except JWTError as exc:  # 过期/签名错误/格式错误 统一按未认证处理
        raise UnauthorizedError("凭证无效或已过期") from exc
