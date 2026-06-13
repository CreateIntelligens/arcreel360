"""
認證核心模組

提供密碼生成、JWT token 建立/驗證、憑據校驗等功能。
同時支援 API Key 認證（`arc-` 字首的 Bearer token）。
"""

import hashlib
import logging
import os
import secrets
import string
import time
from collections import OrderedDict
from datetime import UTC
from pathlib import Path
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Query
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from pydantic import BaseModel, ConfigDict

from lib import PROJECT_ROOT

logger = logging.getLogger(__name__)


class CurrentUserInfo(BaseModel):
    """Current authenticated user info."""

    id: str
    sub: str
    role: str = "admin"

    model_config = ConfigDict(frozen=True)


# JWT 簽名金鑰快取
_cached_token_secret: str | None = None

# Token 有效期：7 天
TOKEN_EXPIRY_SECONDS = 7 * 24 * 3600

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)

# 密碼雜湊
_password_hash = PasswordHash.recommended()
_cached_password_hash: str | None = None


def generate_password(length: int = 16) -> str:
    """生成隨機字母數字密碼"""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def get_token_secret() -> str:
    """獲取 JWT 簽名金鑰

    優先使用 AUTH_TOKEN_SECRET 環境變數，否則自動生成並快取。
    """
    global _cached_token_secret

    env_secret = os.environ.get("AUTH_TOKEN_SECRET")
    if env_secret:
        return env_secret

    if _cached_token_secret is not None:
        return _cached_token_secret

    _cached_token_secret = secrets.token_hex(32)
    logger.info("已自動生成 JWT 簽名金鑰")
    return _cached_token_secret


def create_token(username: str) -> str:
    """建立 JWT token

    Args:
        username: 使用者名稱

    Returns:
        JWT token 字串
    """
    now = time.time()
    payload = {
        "sub": username,
        "iat": now,
        "exp": now + TOKEN_EXPIRY_SECONDS,
    }
    return jwt.encode(payload, get_token_secret(), algorithm="HS256")


def verify_token(token: str) -> dict | None:
    """驗證 JWT token

    Args:
        token: JWT token 字串

    Returns:
        成功返回 payload dict，失敗返回 None
    """
    try:
        payload = jwt.decode(token, get_token_secret(), algorithms=["HS256"])
        return payload
    except (jwt.InvalidTokenError, jwt.ExpiredSignatureError):
        return None


DOWNLOAD_TOKEN_EXPIRY_SECONDS = 300  # 5 分鐘


def create_download_token(username: str, project_name: str) -> str:
    """簽發短時效下載 token，用於瀏覽器原生下載認證"""
    now = time.time()
    payload = {
        "sub": username,
        "project": project_name,
        "purpose": "download",
        "iat": now,
        "exp": now + DOWNLOAD_TOKEN_EXPIRY_SECONDS,
    }
    return jwt.encode(payload, get_token_secret(), algorithm="HS256")


def verify_download_token(token: str, project_name: str) -> dict:
    """驗證下載 token

    Returns:
        成功返回 payload dict

    Raises:
        jwt.ExpiredSignatureError: token 已過期
        jwt.InvalidTokenError: token 無效
        ValueError: purpose 或 project 不匹配
    """
    payload = jwt.decode(token, get_token_secret(), algorithms=["HS256"])
    if payload.get("purpose") != "download":
        raise ValueError("token purpose 不匹配")
    if payload.get("project") != project_name:
        raise ValueError("token project 不匹配")
    return payload


def _get_password_hash() -> str:
    """獲取當前密碼的雜湊值（快取）"""
    global _cached_password_hash
    if _cached_password_hash is None:
        raw = os.environ.get("AUTH_PASSWORD", "")
        _cached_password_hash = _password_hash.hash(raw)
    return _cached_password_hash


def check_credentials(username: str, password: str) -> bool:
    """校驗使用者名稱密碼（使用雜湊比對）

    從 AUTH_USERNAME（預設 admin）和 AUTH_PASSWORD 環境變數讀取。
    即使使用者名稱不匹配也執行雜湊驗證，防止時序攻擊。
    """
    expected_username = os.environ.get("AUTH_USERNAME", "admin")
    pw_hash = _get_password_hash()
    username_ok = secrets.compare_digest(username, expected_username)
    password_ok = _password_hash.verify(password, pw_hash)
    return username_ok and password_ok


def ensure_auth_password(env_path: str | None = None) -> str:
    """確保 AUTH_PASSWORD 已設定

    如果 AUTH_PASSWORD 環境變數為空，自動生成密碼，寫入環境變數，
    回寫到 .env 檔案，並用 logger.warning 輸出到控制檯。

    Args:
        env_path: .env 檔案路徑，預設為專案根目錄的 .env

    Returns:
        當前的 AUTH_PASSWORD 值
    """
    password = os.environ.get("AUTH_PASSWORD")
    if password:
        return password

    # 自動生成密碼
    password = generate_password()
    os.environ["AUTH_PASSWORD"] = password

    # 回寫到 .env 檔案
    if env_path is None:
        env_path = str(PROJECT_ROOT / ".env")

    env_file = Path(env_path)
    try:
        if env_file.exists():
            lines = env_file.read_text().splitlines()
            new_lines = []
            found = False
            for line in lines:
                if not found and line.strip().startswith("AUTH_PASSWORD="):
                    new_lines.append(f"AUTH_PASSWORD={password}")
                    found = True
                else:
                    new_lines.append(line)
            if not found:
                new_lines.append(f"AUTH_PASSWORD={password}")
            new_content = "\n".join(new_lines) + "\n"
            # 使用原地寫入（truncate + write）保留 inode，相容 Docker bind mount
            with open(env_file, "r+") as f:
                f.seek(0)
                f.write(new_content)
                f.truncate()
        else:
            env_file.write_text(f"AUTH_PASSWORD={password}\n")
    except OSError:
        logger.warning("無法寫入 .env 檔案: %s", env_path)

    logger.warning("已自動生成認證密碼，請檢視 .env 檔案中的 AUTH_PASSWORD 欄位")
    return password


# ---------------------------------------------------------------------------
# API Key 認證支援
# ---------------------------------------------------------------------------

API_KEY_PREFIX = "arc-"
API_KEY_CACHE_TTL = 300  # 5 分鐘

# LRU 快取：key_hash → (payload_dict | None, expires_at_timestamp)
# payload 為 None 表示 key 不存在或已過期（負快取）
# 使用 OrderedDict 實現 LRU：命中時 move_to_end，淘汰時 popitem(last=False)
_api_key_cache: OrderedDict[str, tuple[dict | None, float]] = OrderedDict()
_API_KEY_CACHE_MAX = 512


def _hash_api_key(key: str) -> str:
    """計算 API Key 的 SHA-256 雜湊。"""
    return hashlib.sha256(key.encode()).hexdigest()


def invalidate_api_key_cache(key_hash: str) -> None:
    """立即清除指定 key_hash 的快取條目（key 刪除時呼叫）。"""
    _api_key_cache.pop(key_hash, None)


def _get_cached_api_key_payload(key_hash: str) -> tuple[bool, dict | None]:
    """從快取中查詢。返回 (命中, payload 或 None)。命中時將條目移至末尾（LRU）。"""
    entry = _api_key_cache.get(key_hash)
    if entry is None:
        return False, None
    payload, expiry = entry
    if time.monotonic() > expiry:
        _api_key_cache.pop(key_hash, None)
        return False, None
    _api_key_cache.move_to_end(key_hash)
    return True, payload


def _set_api_key_cache(key_hash: str, payload: dict | None, expires_at_ts: float | None = None) -> None:
    """寫入快取（含 LRU 淘汰）。

    正向快取（payload 非 None）TTL 以 key 實際過期時間為上界，
    避免 key 過期後仍在快取中透過驗證的安全問題。
    """
    if len(_api_key_cache) >= _API_KEY_CACHE_MAX:
        # 淘汰最久未使用的條目（LRU：OrderedDict 頭部）
        _api_key_cache.popitem(last=False)
    ttl = API_KEY_CACHE_TTL
    if payload is not None and expires_at_ts is not None:
        time_to_expiry = expires_at_ts - time.monotonic()
        if time_to_expiry <= 0:
            # key 已過期，寫入負快取
            _api_key_cache[key_hash] = (None, time.monotonic() + API_KEY_CACHE_TTL)
            return
        ttl = min(ttl, time_to_expiry)
    _api_key_cache[key_hash] = (payload, time.monotonic() + ttl)


async def _verify_api_key(token: str) -> dict | None:
    """驗證 API Key token，返回 payload dict 或 None（失敗/過期/不存在）。

    內部先查快取，快取未命中再查資料庫。
    查庫成功後更新 last_used_at（後臺非同步，不阻塞響應）。
    """
    key_hash = _hash_api_key(token)

    # 快取查詢
    hit, cached_payload = _get_cached_api_key_payload(key_hash)
    if hit:
        return cached_payload

    # 資料庫查詢
    from lib.db import async_session_factory
    from lib.db.repositories.api_key_repository import ApiKeyRepository

    async with async_session_factory() as session:
        async with session.begin():
            repo = ApiKeyRepository(session)
            row = await repo.get_by_hash(key_hash)

    if row is None:
        _set_api_key_cache(key_hash, None)
        return None

    # 檢查過期
    expires_at = row.get("expires_at")
    expires_at_monotonic: float | None = None
    if expires_at:
        from datetime import datetime

        try:
            exp_dt = expires_at
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=UTC)
            if datetime.now(UTC) >= exp_dt:
                _set_api_key_cache(key_hash, None)
                return None
            # 將過期時刻轉換為 monotonic 時間戳，供快取 TTL 上界計算
            remaining_secs = (exp_dt - datetime.now(UTC)).total_seconds()
            expires_at_monotonic = time.monotonic() + remaining_secs
        except (ValueError, TypeError):
            logger.warning("API Key expires_at 值格式無法解析，忽略過期檢查: %r", expires_at)

    payload = {"sub": f"apikey:{row['name']}", "via": "apikey"}
    _set_api_key_cache(key_hash, payload, expires_at_ts=expires_at_monotonic)

    # 非同步更新 last_used_at（不阻塞，儲存引用防止 GC）
    import asyncio

    async def _touch():
        try:
            async with async_session_factory() as s:
                async with s.begin():
                    await ApiKeyRepository(s).touch_last_used(key_hash)
        except Exception:
            logger.exception("更新 API Key last_used_at 失敗（非致命）")

    _touch_task = asyncio.create_task(_touch())
    _touch_task.add_done_callback(lambda _: None)  # suppress "never retrieved" warning

    return payload


def _verify_and_get_payload(token: str) -> dict:
    """同步驗證 JWT token 並在失敗時丟擲 401 異常。（僅用於 JWT 路徑）"""
    payload = verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=401,
            detail="token 無效或已過期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


async def _verify_and_get_payload_async(token: str) -> dict:
    """非同步驗證 token，支援 API Key（arc- 字首）和 JWT 兩種模式。"""
    if token.startswith(API_KEY_PREFIX):
        payload = await _verify_api_key(token)
        if payload is None:
            raise HTTPException(
                status_code=401,
                detail="API Key 無效、已過期或不存在",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload
    # JWT 路徑
    return _verify_and_get_payload(token)


def _payload_to_user(payload: dict) -> CurrentUserInfo:
    """Convert a verified JWT/API-key payload to CurrentUserInfo."""
    from lib.db.base import DEFAULT_USER_ID

    sub = payload.get("sub", "")
    return CurrentUserInfo(id=DEFAULT_USER_ID, sub=sub, role="admin")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> CurrentUserInfo:
    """標準認證依賴 — 支援 JWT 和 API Key Bearer token。"""
    payload = await _verify_and_get_payload_async(token)
    return _payload_to_user(payload)


async def get_current_user_flexible(
    token: Annotated[str | None, Depends(oauth2_scheme_optional)] = None,
    query_token: str | None = Query(None, alias="token"),
) -> CurrentUserInfo:
    """SSE 認證依賴 — 同時支援 Authorization header 和 ?token= query param。"""
    raw = token or query_token
    if not raw:
        raise HTTPException(
            status_code=401,
            detail="缺少認證 token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = await _verify_and_get_payload_async(raw)
    return _payload_to_user(payload)


# Type aliases for FastAPI dependency injection
CurrentUser = Annotated[CurrentUserInfo, Depends(get_current_user)]
CurrentUserFlexible = Annotated[CurrentUserInfo, Depends(get_current_user_flexible)]
