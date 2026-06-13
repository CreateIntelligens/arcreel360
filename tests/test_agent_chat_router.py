"""
同步 Agent 對話端點測試

測試 POST /api/v1/agent/chat 端點的核心邏輯。
"""

from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.agent_runtime.runtime_provider import ProviderUnavailableError, UnsupportedCapabilityError
from server.auth import CurrentUserInfo, get_current_user
from server.routers import agent_chat


def _make_client() -> TestClient:
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: CurrentUserInfo(id="default", sub="testuser", role="admin")
    app.include_router(agent_chat.router, prefix="/api/v1")
    return TestClient(app)


def _fake_session(session_id: str = "sess-1", project_name: str = "demo"):
    meta = MagicMock()
    meta.id = session_id
    meta.project_name = project_name
    return meta


class TestAgentChatEndpoint:
    def _patch_service(
        self, monkeypatch, *, project_exists=True, reply_text="你好", status="completed", session_id="sess-1"
    ):
        """構建 mock AssistantService 並注入。"""
        mock_service = AsyncMock()

        # 專案存在性檢查
        pm = MagicMock()
        if project_exists:
            pm.get_project_path = MagicMock(return_value="/fake/path")
        else:
            pm.get_project_path = MagicMock(side_effect=FileNotFoundError("not found"))
        mock_service.pm = pm

        # 會話查詢（用於歸屬校驗）
        mock_service.get_session = AsyncMock(return_value=_fake_session(session_id=session_id))

        # 統一傳送端點
        mock_service.send_or_create = AsyncMock(return_value={"status": "accepted", "session_id": session_id})

        monkeypatch.setattr(agent_chat, "get_assistant_service", lambda: mock_service)
        monkeypatch.setattr(
            agent_chat,
            "_collect_reply",
            AsyncMock(return_value=(reply_text, status)),
        )
        return mock_service

    def test_new_session_returns_reply(self, monkeypatch):
        self._patch_service(monkeypatch, reply_text="已為你生成劇本")
        with _make_client() as client:
            resp = client.post(
                "/api/v1/agent/chat",
                json={
                    "project_name": "demo",
                    "message": "幫我寫劇本",
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["reply"] == "已為你生成劇本"
        assert body["status"] == "completed"
        assert "session_id" in body

    def test_reuse_existing_session(self, monkeypatch):
        self._patch_service(monkeypatch, reply_text="繼續對話")
        with _make_client() as client:
            resp = client.post(
                "/api/v1/agent/chat",
                json={
                    "project_name": "demo",
                    "message": "繼續",
                    "session_id": "sess-1",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["session_id"] == "sess-1"

    def test_project_not_found_returns_404(self, monkeypatch):
        self._patch_service(monkeypatch, project_exists=False)
        with _make_client() as client:
            resp = client.post(
                "/api/v1/agent/chat",
                json={
                    "project_name": "nonexistent",
                    "message": "test",
                },
            )
        assert resp.status_code == 404

    def test_timeout_status_propagated(self, monkeypatch):
        self._patch_service(monkeypatch, reply_text="部分響應", status="timeout")
        with _make_client() as client:
            resp = client.post(
                "/api/v1/agent/chat",
                json={
                    "project_name": "demo",
                    "message": "長時間任務",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "timeout"
        assert resp.json()["reply"] == "部分響應"

    def test_provider_specific_session_id_is_preserved(self, monkeypatch):
        self._patch_service(monkeypatch, reply_text="Gemini 回覆", session_id="gemini:session-1")
        with _make_client() as client:
            resp = client.post(
                "/api/v1/agent/chat",
                json={
                    "project_name": "demo",
                    "message": "繼續",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["session_id"] == "gemini:session-1"

    def test_unsupported_capability_returns_409(self, monkeypatch):
        mock_service = self._patch_service(monkeypatch)
        mock_service.send_or_create = AsyncMock(
            side_effect=UnsupportedCapabilityError("gemini-lite", "resume", "lite provider 不支援 resume")
        )
        with _make_client() as client:
            resp = client.post(
                "/api/v1/agent/chat",
                json={
                    "project_name": "demo",
                    "message": "繼續",
                },
            )
        assert resp.status_code == 409
        payload = resp.json()["detail"]
        assert payload["error"] == "unsupported_capability"
        assert payload["provider"] == "gemini-lite"
        assert payload["capability"] == "resume"

    def test_provider_unavailable_returns_503(self, monkeypatch):
        mock_service = self._patch_service(monkeypatch)
        mock_service.send_or_create = AsyncMock(side_effect=ProviderUnavailableError("openai-lite"))
        with _make_client() as client:
            resp = client.post(
                "/api/v1/agent/chat",
                json={
                    "project_name": "demo",
                    "message": "繼續",
                },
            )
        assert resp.status_code == 503
        assert "openai-lite" in resp.json()["detail"]


class TestExtractTextFromAssistantMessage:
    def test_list_content(self):
        msg = {"type": "assistant", "content": [{"type": "text", "text": "你好"}]}
        assert agent_chat._extract_text_from_assistant_message(msg) == "你好"

    def test_string_content(self):
        msg = {"type": "assistant", "content": "直接文字"}
        assert agent_chat._extract_text_from_assistant_message(msg) == "直接文字"

    def test_multiple_text_blocks(self):
        msg = {
            "type": "assistant",
            "content": [
                {"type": "text", "text": "第一段"},
                {"type": "tool_use", "name": "Read"},
                {"type": "text", "text": "第二段"},
            ],
        }
        assert agent_chat._extract_text_from_assistant_message(msg) == "第一段第二段"

    def test_no_text_blocks(self):
        msg = {"type": "assistant", "content": [{"type": "tool_use", "name": "Read"}]}
        assert agent_chat._extract_text_from_assistant_message(msg) == ""
