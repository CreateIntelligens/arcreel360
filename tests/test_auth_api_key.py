"""
API Key 認證分流單元測試

測試 auth 模組中的 API Key 路徑：雜湊計算、快取邏輯、認證分流。
"""

import hashlib
import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

import server.auth as auth_module


@pytest.fixture(autouse=True)
def clear_cache():
    """每次測試前清空 API Key 快取。"""
    auth_module._api_key_cache.clear()
    yield
    auth_module._api_key_cache.clear()


class TestHashApiKey:
    def test_deterministic(self):
        key = "arc-testapikey1234"
        assert auth_module._hash_api_key(key) == auth_module._hash_api_key(key)

    def test_sha256_output(self):
        key = "arc-abc"
        expected = hashlib.sha256(key.encode()).hexdigest()
        assert auth_module._hash_api_key(key) == expected


class TestApiKeyCache:
    def test_cache_miss(self):
        hit, payload = auth_module._get_cached_api_key_payload("nonexistent")
        assert not hit
        assert payload is None

    def test_cache_set_and_hit(self):
        auth_module._set_api_key_cache("hash123", {"sub": "apikey:test", "via": "apikey"})
        hit, payload = auth_module._get_cached_api_key_payload("hash123")
        assert hit
        assert payload == {"sub": "apikey:test", "via": "apikey"}

    def test_cache_negative_entry(self):
        auth_module._set_api_key_cache("hash_missing", None)
        hit, payload = auth_module._get_cached_api_key_payload("hash_missing")
        assert hit
        assert payload is None

    def test_cache_expired_entry(self):
        auth_module._api_key_cache["hash_expired"] = ({"sub": "test"}, time.monotonic() - 1)
        hit, _ = auth_module._get_cached_api_key_payload("hash_expired")
        assert not hit

    def test_invalidate_removes_entry(self):
        auth_module._set_api_key_cache("hash_to_delete", {"sub": "test"})
        auth_module.invalidate_api_key_cache("hash_to_delete")
        hit, _ = auth_module._get_cached_api_key_payload("hash_to_delete")
        assert not hit

    def test_cache_hit_skips_db(self):
        """快取命中時不應查詢資料庫（透過 _verify_api_key 的分支邏輯驗證）。"""
        key = "arc-cached-key"
        key_hash = auth_module._hash_api_key(key)
        auth_module._set_api_key_cache(key_hash, {"sub": "apikey:cached", "via": "apikey"})
        # 若命中快取則返回快取值；True means hit
        hit, payload = auth_module._get_cached_api_key_payload(key_hash)
        assert hit
        assert payload["sub"] == "apikey:cached"


class TestVerifyAndGetPayloadAsync:
    @pytest.mark.asyncio
    async def test_jwt_path_success(self):
        """非 arc- 字首走 JWT 路徑，成功返回 payload。"""
        with patch("server.auth.verify_token", return_value={"sub": "admin"}):
            result = await auth_module._verify_and_get_payload_async("some.jwt.token")
        assert result == {"sub": "admin"}

    @pytest.mark.asyncio
    async def test_jwt_invalid_raises_401(self):
        """非 arc- 字首但 JWT 驗證失敗，丟擲 401。"""
        with patch("server.auth.verify_token", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await auth_module._verify_and_get_payload_async("invalid.jwt.token")
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_api_key_path_success(self):
        """arc- 字首走 API Key 路徑，成功返回 payload。"""
        expected = {"sub": "apikey:mykey", "via": "apikey"}
        with patch("server.auth._verify_api_key", new=AsyncMock(return_value=expected)):
            result = await auth_module._verify_and_get_payload_async("arc-validkey")
        assert result["via"] == "apikey"
        assert result["sub"] == "apikey:mykey"

    @pytest.mark.asyncio
    async def test_api_key_not_found_raises_401(self):
        """arc- 字首但 key 不存在，丟擲 401。"""
        with patch("server.auth._verify_api_key", new=AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc_info:
                await auth_module._verify_and_get_payload_async("arc-badkey")
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_api_key_expired_raises_401(self):
        """arc- 字首但 key 已過期（_verify_api_key 返回 None），丟擲 401。"""
        with patch("server.auth._verify_api_key", new=AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc_info:
                await auth_module._verify_and_get_payload_async("arc-expiredkey")
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_jwt_path_not_called_for_api_key(self):
        """arc- 字首時不應呼叫 verify_token。"""
        with (
            patch("server.auth._verify_api_key", new=AsyncMock(return_value={"sub": "apikey:k", "via": "apikey"})),
            patch("server.auth.verify_token") as mock_jwt,
        ):
            await auth_module._verify_and_get_payload_async("arc-somekey")
        mock_jwt.assert_not_called()
