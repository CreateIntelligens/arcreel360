"""
認證依賴注入整合測試

測試替換中介軟體後，各路徑的認證行為是否正確。
"""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import server.auth as auth_module


@pytest.fixture(autouse=True)
def _auth_env():
    """為所有測試設定固定的認證環境變數，測試結束後清理快取。"""
    auth_module._cached_token_secret = None
    auth_module._cached_password_hash = None
    with patch.dict(
        os.environ,
        {
            "AUTH_USERNAME": "testuser",
            "AUTH_PASSWORD": "testpass",
            "AUTH_TOKEN_SECRET": "test-middleware-secret-key-at-least-32-bytes",
        },
    ):
        yield
    auth_module._cached_token_secret = None
    auth_module._cached_password_hash = None


@pytest.fixture()
def client():
    """建立使用真實 app 的測試客戶端。"""
    from unittest.mock import AsyncMock, MagicMock

    from server.app import app

    # Mock 掉 GenerationWorker，避免啟動背景執行緒及相關資料庫操作
    mock_worker = MagicMock()
    mock_worker.start = AsyncMock()
    mock_worker.stop = AsyncMock()

    with patch("server.app.create_generation_worker", return_value=mock_worker):
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


def _login(client: TestClient) -> str:
    """輔助函式：登入並返回 access_token。"""
    resp = client.post(
        "/api/v1/auth/token",
        data={"username": "testuser", "password": "testpass"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


class TestAuthIntegration:
    def test_health_no_auth(self, client):
        """GET /health 不需要認證，返回 200"""
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_login_no_auth(self, client):
        """POST /api/v1/auth/token 不需要認證"""
        resp = client.post(
            "/api/v1/auth/token",
            data={"username": "testuser", "password": "testpass"},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_api_without_token(self, client):
        """GET /api/v1/projects 缺少 token 返回 401"""
        resp = client.get("/api/v1/projects")
        assert resp.status_code == 401

    def test_api_with_valid_token(self, client):
        """先登入獲取 token，再帶 token 訪問 API，不應返回 401"""
        token = _login(client)
        resp = client.get(
            "/api/v1/projects",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code != 401

    def test_api_with_invalid_token(self, client):
        """帶無效 token 訪問返回 401"""
        resp = client.get(
            "/api/v1/projects",
            headers={"Authorization": "Bearer invalid-token-value"},
        )
        assert resp.status_code == 401

    def test_docs_page_accessible(self, client):
        """/docs Swagger UI 應可訪問"""
        resp = client.get("/docs")
        assert resp.status_code == 200

    def test_frontend_path_no_auth(self, client):
        """前端路徑（非 /api/ 開頭）不需要認證"""
        resp = client.get("/app/projects")
        assert resp.status_code != 401
