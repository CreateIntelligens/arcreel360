"""
認證 API 路由

提供 OAuth2 登入和 token 驗證介面。
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from server.auth import CurrentUser, check_credentials, create_token

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== 響應模型 ====================


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


class VerifyResponse(BaseModel):
    valid: bool
    username: str


# ==================== 路由 ====================


@router.post("/auth/token", response_model=TokenResponse)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
):
    """使用者登入

    使用 OAuth2 標準表單格式驗證憑據，成功返回 access_token。
    """
    if not check_credentials(form_data.username, form_data.password):
        logger.warning("登入失敗: 使用者名稱或密碼錯誤 (使用者: %s)", form_data.username)
        raise HTTPException(
            status_code=401,
            detail="使用者名稱或密碼錯誤",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_token(form_data.username)
    logger.info("使用者登入成功: %s", form_data.username)
    return TokenResponse(access_token=token, token_type="bearer")


@router.get("/auth/verify", response_model=VerifyResponse)
async def verify(
    current_user: CurrentUser,
):
    """驗證 token 有效性

    使用 OAuth2 Bearer token 依賴自動提取和驗證 token。
    """
    return VerifyResponse(valid=True, username=current_user.sub)
