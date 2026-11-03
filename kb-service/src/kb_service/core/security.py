from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import cast

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, ValidationError

from kb_service.core.config import get_settings
from kb_service.core.exceptions import UnauthorizedError

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenClaims(BaseModel):
    """JWT 载荷的业务契约（decode 之后的方向）。

    注意 exp/iat 在 decode 后是 Unix 秒（int），不是 datetime ——
    编码方向塞 datetime，解码方向拿回来 int，两个方向不能共用一套类型。
    """

    sub: str
    iat: int | None = None
    exp: int | None = None


def hash_password(raw: str) -> str:
    return _pwd_ctx.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    return _pwd_ctx.verify(raw, hashed)


def create_access_token(subject: str, extra: Mapping[str, object] | None = None) -> str:
    """签发 JWT。subject 一般是 user_id。"""
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        **(extra or {}),
    }
    # python-jose 没有类型标注（pyproject 只对 jose.* 关掉了 import 检查），
    # jwt.encode 的返回值在 mypy 眼里是 Any；strict 的 no-any-return 不允许把 Any
    # 直接 return 出去，所以这里必须收敛一次。
    #
    # 这个 cast 和"拿 cast 假装修好数据"不是一回事：
    #   - 这里收敛的是**第三方库的类型缺口**——jose 文档承诺返回 str，只是没写注解，
    #     Any 来自库、不来自用户数据，运行时行为由库保证。
    #   - 反例（D4 坑①）：cast(str, row.get("name")) 是把**外部未知值**谎称成 str，
    #     None 照样传下去，错误延迟到远处才炸。
    # 换掉 jose 或 W14 接真实鉴权时，复验一次返回值仍是 str。
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
    return cast(str, token)


def decode_access_token(token: str) -> TokenClaims:
    settings = get_settings()
    try:
        raw = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError as exc:  # 过期/签名错误/格式错误 统一按未认证处理
        raise UnauthorizedError("凭证无效或已过期") from exc

    try:
        return TokenClaims.model_validate(raw)
    except ValidationError as exc:
        raise UnauthorizedError("凭证载荷不合法") from exc
