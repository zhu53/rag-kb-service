from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from kb_service.core import constants
from kb_service.core.config import get_settings
from kb_service.core.db import get_db
from kb_service.repositories.user_repo import UserRepository
from kb_service.schemas.auth import LoginIn, RefreshIn, RegisterIn, TokenOut, UserOut
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
    access, refresh = AuthService(UserRepository(session), session=session).login(body)
    return TokenOut(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/logout", status_code=204, summary="退出登录：作废 refresh 票")
async def logout(body: RefreshIn, session: Session = Depends(get_db)) -> None:
    AuthService(UserRepository(session), session=session).logout(body)


@router.post("/refresh", summary="换取新票")
async def refresh(body: RefreshIn, session: Session = Depends(get_db)) -> TokenOut:
    settings = get_settings()
    access, new_refresh = AuthService(UserRepository(session), session=session).refresh(body)
    return TokenOut(
        access_token=access,
        refresh_token=new_refresh,
        expires_in=settings.access_token_expire_minutes * 60,
    )
