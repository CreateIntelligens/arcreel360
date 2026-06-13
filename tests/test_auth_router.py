"""
登入 API 路由測試

測試 server.routers.auth 中的登入和 token 驗證路由。
"""

import os
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import server.auth as auth_module
from server.routers import auth as auth_router


@pytest.fixture()
def client():
    """建立測試客戶端，設定固定的認證環境變數"""
    auth_module._cached_token_secret = None
    auth_module._cached_password_hash = None
    with patch.dict(
        os.environ,
        {
            "AUTH_USERNAME": "testuser",
            "AUTH_PASSWORD": "testpass",
            "AUTH_TOKEN_SECRET": "test-router-secret-key-at-least-32-bytes-long",
        },
    ):
        app = FastAPI()
        app.include_router(auth_router.router, prefix="/api/v1")
        with TestClient(app) as c:
            yield c


class TestLoginRoute:
    def test_login_success(self, client):
        """正確憑據返回 200 + access_token"""
        resp = client.post(
            "/api/v1/auth/token",
            data={"username": "testuser", "password": "testpass"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 0

    def test_login_wrong_password(self, client):
        """錯誤密碼返回 401"""
        resp = client.post(
            "/api/v1/auth/token",
            data={"username": "testuser", "password": "wrongpass"},
        )
        assert resp.status_code == 401

    def test_login_wrong_username(self, client):
        """錯誤使用者名稱返回 401"""
        resp = client.post(
            "/api/v1/auth/token",
            data={"username": "wronguser", "password": "testpass"},
        )
        assert resp.status_code == 401


class TestVerifyRoute:
    def test_verify_valid_token(self, client):
        """有效 token 驗證透過"""
        login_resp = client.post(
            "/api/v1/auth/token",
            data={"username": "testuser", "password": "testpass"},
        )
        token = login_resp.json()["access_token"]

        resp = client.get(
            "/api/v1/auth/verify",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["username"] == "testuser"

    def test_verify_no_token(self, client):
        """缺少 token 返回 401"""
        resp = client.get("/api/v1/auth/verify")
        assert resp.status_code == 401

    def test_verify_invalid_token(self, client):
        """無效 token 返回 401"""
        resp = client.get(
            "/api/v1/auth/verify",
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert resp.status_code == 401
