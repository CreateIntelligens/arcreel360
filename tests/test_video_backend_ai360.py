"""ai360 影片後端單元測試。

以假的 httpx.AsyncClient 腳本化各端點回應，驗證登入 → 解析專案 →
（可選上傳起始圖）→ 建立任務 → 輪詢 → 下載 的完整流程。
"""

from __future__ import annotations

from pathlib import Path

import pytest

import lib.video_backends.ai360 as ai360_mod
from lib.video_backends.ai360 import AI360VideoBackend
from lib.video_backends.base import VideoCapability, VideoGenerationRequest


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    """依 URL 後綴回傳腳本化回應的假 httpx client。"""

    # 由測試在實例化前以類別屬性注入腳本與呼叫記錄
    script: dict[str, dict] = {}
    calls: list[tuple[str, str, dict]] = []

    def __init__(self, *args, **kwargs):
        pass

    @classmethod
    def reset(cls) -> None:
        cls.script = {}
        cls.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def _match(self, url: str) -> dict:
        for suffix, payload in self.script.items():
            if url.endswith(suffix):
                return payload
        raise AssertionError(f"未腳本化的 URL: {url}")

    async def post(self, url: str, **kwargs) -> _FakeResponse:
        type(self).calls.append(("POST", url, kwargs))
        return _FakeResponse(self._match(url))

    async def get(self, url: str, **kwargs) -> _FakeResponse:
        type(self).calls.append(("GET", url, kwargs))
        return _FakeResponse(self._match(url))


@pytest.fixture
def _patch_client(monkeypatch):
    """以 _FakeAsyncClient 取代 httpx.AsyncClient，並重置呼叫記錄。"""
    _FakeAsyncClient.reset()
    monkeypatch.setattr(ai360_mod.httpx, "AsyncClient", _FakeAsyncClient)
    return _FakeAsyncClient


@pytest.fixture
def _patch_download(monkeypatch):
    """攔截 download_video，記錄被請求下載的 URL，不做真實 I/O。"""
    downloaded: list[str] = []

    async def fake_download(url: str, output_path: Path, **kwargs) -> None:
        downloaded.append(url)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-video")

    monkeypatch.setattr(ai360_mod, "download_video", fake_download)
    return downloaded


def test_requires_credentials():
    with pytest.raises(ValueError, match="username"):
        AI360VideoBackend(username="", password="p", base_url="https://x")
    with pytest.raises(ValueError, match="base_url"):
        AI360VideoBackend(username="u", password="p", base_url="")


def test_capabilities():
    backend = AI360VideoBackend(username="u", password="p", base_url="https://x")
    assert VideoCapability.TEXT_TO_VIDEO in backend.capabilities
    assert VideoCapability.IMAGE_TO_VIDEO in backend.capabilities
    assert backend.name == "ai360"
    assert backend.model == "ai360-video"


async def test_text_to_video_full_flow(tmp_path, _patch_client, _patch_download):
    _patch_client.script = {
        "/api/auth/login": {"ok": True, "token": "jwt-token"},
        "/api/projects": {"ok": True, "projects": [{"id": 42}]},
        "/api/video/create": {"ok": True, "historyId": 123, "task": {"status": "submitted"}},
        "/api/history/123": {
            "ok": True,
            "task": {"id": 123, "status": "succeeded", "videoUrl": "/generated/videos/v.mp4"},
        },
    }

    backend = AI360VideoBackend(username="u", password="p", base_url="https://x.com")
    out = tmp_path / "out.mp4"
    req = VideoGenerationRequest(
        prompt="貓在草原奔跑",
        output_path=out,
        aspect_ratio="16:9",
        duration_seconds=8,
        resolution="720p",
        generate_audio=True,
    )
    result = await backend.generate(req)

    assert result.provider == "ai360"
    assert result.task_id == "123"
    assert result.duration_seconds == 8
    assert result.generate_audio is True
    assert result.video_uri == "https://x.com/generated/videos/v.mp4"
    assert out.read_bytes() == b"fake-video"
    assert _patch_download == ["https://x.com/generated/videos/v.mp4"]

    # create 請求帶正確的 X-Project-Id 與 payload
    create_call = next(c for c in _patch_client.calls if c[1].endswith("/api/video/create"))
    assert create_call[2]["headers"]["X-Project-Id"] == "42"
    assert create_call[2]["json"]["ratio"] == "16:9"
    assert create_call[2]["json"]["generateAudio"] is True


async def test_image_to_video_uploads_and_prefixes_token(tmp_path, _patch_client, _patch_download):
    start_image = tmp_path / "ref.png"
    start_image.write_bytes(b"img")

    _patch_client.script = {
        "/api/auth/login": {"ok": True, "token": "jwt-token"},
        "/api/projects": {"ok": True, "projects": [{"id": 7}]},
        "/api/assets/upload": {
            "ok": True,
            "assets": {"items": {"image": [{"id": 1, "token": "@圖片1"}]}},
        },
        "/api/video/create": {"ok": True, "historyId": 9, "task": {"status": "submitted"}},
        "/api/history/9": {
            "ok": True,
            "task": {"status": "succeeded", "outputs": [{"kind": "video", "url": "/g/v.mp4"}]},
        },
    }

    backend = AI360VideoBackend(username="u", password="p", base_url="https://x.com", project_id="7")
    req = VideoGenerationRequest(
        prompt="走進咖啡廳",
        output_path=tmp_path / "o.mp4",
        start_image=start_image,
    )
    await backend.generate(req)

    create_call = next(c for c in _patch_client.calls if c[1].endswith("/api/video/create"))
    assert create_call[2]["json"]["prompt"] == "@圖片1 走進咖啡廳"


async def test_failed_status_raises(tmp_path, _patch_client, _patch_download):
    _patch_client.script = {
        "/api/auth/login": {"ok": True, "token": "t"},
        "/api/projects": {"ok": True, "projects": [{"id": 1}]},
        "/api/video/create": {"ok": True, "historyId": 5},
        "/api/history/5": {"ok": True, "task": {"status": "failed", "errorMessage": "提示詞不符規範"}},
    }

    backend = AI360VideoBackend(username="u", password="p", base_url="https://x.com")
    req = VideoGenerationRequest(prompt="x", output_path=tmp_path / "o.mp4")
    with pytest.raises(RuntimeError, match="提示詞不符規範"):
        await backend.generate(req)


async def test_no_projects_raises(tmp_path, _patch_client):
    _patch_client.script = {
        "/api/auth/login": {"ok": True, "token": "t"},
        "/api/projects": {"ok": True, "projects": []},
    }
    backend = AI360VideoBackend(username="u", password="p", base_url="https://x.com")
    req = VideoGenerationRequest(prompt="x", output_path=tmp_path / "o.mp4")
    with pytest.raises(RuntimeError, match="沒有可用專案"):
        await backend.generate(req)
