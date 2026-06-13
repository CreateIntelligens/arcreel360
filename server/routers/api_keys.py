"""
API Key 管理路由

提供 API Key 的建立、列表查詢和刪除介面。
"""

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from lib.db import async_session_factory
from lib.db.repositories.api_key_repository import ApiKeyRepository
from server.auth import (
    API_KEY_PREFIX,
    CurrentUser,
    CurrentUserInfo,
    _hash_api_key,
    invalidate_api_key_cache,
)

router = APIRouter()


def _require_jwt_auth(user: CurrentUserInfo) -> None:
    """確保請求透過 JWT 認證（非 API Key）。API Key 管理操作不允許由 API Key 本身執行。"""
    if user.sub.startswith("apikey:"):
        raise HTTPException(status_code=403, detail="API Key 無權執行此操作，請使用 JWT 認證")


API_KEY_DEFAULT_EXPIRY_DAYS = 30


def _generate_api_key() -> str:
    """生成格式為 arc-<32位隨機字元> 的 API Key。"""
    random_part = secrets.token_hex(16)  # 32 hex chars
    return f"{API_KEY_PREFIX}{random_part}"


def _default_expires_at() -> datetime:
    return datetime.now(UTC) + timedelta(days=API_KEY_DEFAULT_EXPIRY_DAYS)


class CreateApiKeyRequest(BaseModel):
    name: str
    expires_days: int | None = Field(None, ge=0)  # None 使用預設 30 天，0 表示不過期


class CreateApiKeyResponse(BaseModel):
    id: int
    name: str
    key: str  # 完整 key，僅在建立時返回
    key_prefix: str
    created_at: str
    expires_at: str | None


class ApiKeyInfo(BaseModel):
    id: int
    name: str
    key_prefix: str
    created_at: str
    expires_at: str | None
    last_used_at: str | None


@router.post("/api-keys", status_code=201)
async def create_api_key(
    body: CreateApiKeyRequest,
    _user: CurrentUser,
) -> CreateApiKeyResponse:
    """建立新 API Key。完整 key 僅在響應中出現一次，之後無法再檢視。"""
    _require_jwt_auth(_user)
    key = _generate_api_key()
    key_hash = _hash_api_key(key)
    key_prefix = key[:8]  # e.g. "arc-abcd"

    if body.expires_days == 0:
        expires_at: datetime | None = None
    elif body.expires_days is not None:
        expires_at = datetime.now(UTC) + timedelta(days=body.expires_days)
    else:
        expires_at = _default_expires_at()

    try:
        async with async_session_factory() as session:
            async with session.begin():
                repo = ApiKeyRepository(session)
                row = await repo.create(
                    name=body.name,
                    key_hash=key_hash,
                    key_prefix=key_prefix,
                    expires_at=expires_at,
                )
    except IntegrityError:
        raise HTTPException(status_code=409, detail=f"名稱 '{body.name}' 已存在")

    return CreateApiKeyResponse(
        id=row["id"],
        name=row["name"],
        key=key,
        key_prefix=row["key_prefix"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
    )


@router.get("/api-keys")
async def list_api_keys(
    _user: CurrentUser,
) -> list[ApiKeyInfo]:
    """查詢所有 API Key 的後設資料（不含完整 key）。"""
    _require_jwt_auth(_user)
    async with async_session_factory() as session:
        async with session.begin():
            repo = ApiKeyRepository(session)
            rows = await repo.list_all()

    return [ApiKeyInfo(**row) for row in rows]


@router.delete("/api-keys/{key_id}", status_code=204)
async def delete_api_key(
    key_id: int,
    _user: CurrentUser,
) -> None:
    """刪除（吊銷）指定 API Key，並立即清除記憶體快取。"""
    _require_jwt_auth(_user)
    async with async_session_factory() as session:
        async with session.begin():
            repo = ApiKeyRepository(session)
            row = await repo.get_by_id(key_id)
            if row is None:
                raise HTTPException(status_code=404, detail=f"API Key {key_id} 不存在")
            key_hash = row["key_hash"]
            # 先失效快取再刪庫：即使事務提交後崩潰，快取也已清除，
            # 不會出現 DB 已刪但快取仍有效的寬限視窗。
            invalidate_api_key_cache(key_hash)
            deleted = await repo.delete(key_id)

    if not deleted:
        raise HTTPException(status_code=404, detail=f"API Key {key_id} 不存在")
