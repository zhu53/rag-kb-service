from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Password = Annotated[str, Field(min_length=8, max_length=72)]


class RegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: Password

    @field_validator("password")
    @classmethod
    def _check_byte_len(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 72:
            raise ValueError("密码不能超过 72 字节（中文约 24 字）")
        return v


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str  # 登录不校验长度（老密码可能不合新规）


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # 秒；让客户端知道什么时候该续


class UserOut(BaseModel):
    id: UUID
    email: EmailStr
    role: str
    created_at: datetime
