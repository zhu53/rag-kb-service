from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from kb_service.core import constants
from kb_service.core.config import get_settings
from kb_service.core.db import get_db
from kb_service.repositories.user_repo import UserRepository
from kb_service.schemas.auth import LoginIn, RegisterIn, TokenOut, UserOut
from kb_service.schemas.common import ApiResponse
from kb_service.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=[constants.TAG_AUTH])


@router.post("/register", status_code=201, summary="注册")
async def register(body: RegisterIn, session: Session = Depends(get_db)) -> ApiResponse[UserOut]:
    row = AuthService(UserRepository(session), session=session).register(body)
    return ApiResponse[UserOut](data=UserOut.model_validate(row))


@router.post("/login", summary="登录，换取 access_token")
async def login(body: LoginIn, session: Session = Depends(get_db)) -> TokenOut:
    settings = get_settings()
    token = AuthService(UserRepository(session), session=session).login(body)
    return TokenOut(access_token=token, expires_in=settings.access_token_expire_minutes * 60)
