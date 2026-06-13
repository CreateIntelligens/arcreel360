from unittest.mock import MagicMock

import pytest

from server.routers.generate import (
    _read_episode_override,
    _snapshot_image_backend,
    _snapshot_video_backend,
)


@pytest.fixture
def mock_pm(monkeypatch):
    pm_mock = MagicMock()
    monkeypatch.setattr("server.routers.generate.get_project_manager", lambda: pm_mock)
    return pm_mock


def test_read_episode_override():
    project = {
        "episodes": [
            {
                "episode": 1,
                "script_file": "scripts/episode_1.json",
                "overrides": {
                    "video_backend": "ark/doubao-seedance-pro",
                    "duration_seconds": 8,
                },
            },
            {
                "episode": 2,
                "script_file": "episode_2.json",
                "overrides": {
                    "video_backend": "openai/gpt-video",
                },
            },
        ]
    }

    # 測試正常讀取
    assert _read_episode_override(project, "scripts/episode_1.json", "video_backend") == "ark/doubao-seedance-pro"
    assert _read_episode_override(project, "episode_1.json", "video_backend") == "ark/doubao-seedance-pro"
    assert _read_episode_override(project, "scripts/episode_2.json", "video_backend") == "openai/gpt-video"
    assert _read_episode_override(project, "episode_2.json", "video_backend") == "openai/gpt-video"
    assert _read_episode_override(project, "scripts/episode_1.json", "duration_seconds") == 8

    # 測試無此 overrides 或欄位為空
    assert _read_episode_override(project, "scripts/episode_1.json", "image_backend") is None
    assert _read_episode_override(project, "scripts/episode_3.json", "video_backend") is None


def test_snapshot_image_backend_with_episode_override(mock_pm, monkeypatch):
    # 模擬 scene overrides 回傳 None
    monkeypatch.setattr("server.routers.generate._read_scene_backend_override", lambda *a, **k: None)

    project_data = {
        "image_backend": "gemini/gemini-image-global",
        "episodes": [
            {
                "episode": 1,
                "script_file": "scripts/episode_1.json",
                "overrides": {
                    "image_backend": "ark/doubao-image-episode",
                    "image_size": "2K",
                },
            }
        ],
    }
    mock_pm.load_project.return_value = project_data

    # 1. 測試當前集數有 overrides
    res = _snapshot_image_backend("demo", script_file="scripts/episode_1.json", resource_id="seg_1")
    assert res["image_provider"] == "ark"
    assert res["image_model"] == "doubao-image-episode"
    assert res["image_size"] == "2K"

    # 2. 測試當前集數沒有 overrides，fallback 至專案層級
    res_fallback = _snapshot_image_backend("demo", script_file="scripts/episode_2.json", resource_id="seg_1")
    assert res_fallback["image_provider"] == "gemini"
    assert res_fallback["image_model"] == "gemini-image-global"
    assert "image_size" not in res_fallback


def test_snapshot_video_backend_with_episode_override(mock_pm, monkeypatch):
    monkeypatch.setattr("server.routers.generate._read_scene_backend_override", lambda *a, **k: None)

    project_data = {
        "video_backend": "gemini/veo-global",
        "episodes": [
            {
                "episode": 1,
                "script_file": "scripts/episode_1.json",
                "overrides": {
                    "video_backend": "ark/doubao-seedance-episode",
                    "video_resolution": "1080p",
                },
            }
        ],
    }
    mock_pm.load_project.return_value = project_data

    # 1. 測試當前集數有 overrides
    res = _snapshot_video_backend("demo", script_file="scripts/episode_1.json", resource_id="seg_1")
    assert res["video_provider"] == "ark"
    assert res["video_provider_settings"] == {"model": "doubao-seedance-episode"}
    assert res["video_resolution"] == "1080p"

    # 2. 測試當前集數沒有 overrides，這時影片後端解析由 _resolve_video_backend 在服務層處理，
    # _snapshot_video_backend 應該只回傳空或只回傳解析度
    res_fallback = _snapshot_video_backend("demo", script_file="scripts/episode_2.json", resource_id="seg_1")
    assert "video_provider" not in res_fallback
    assert "video_resolution" not in res_fallback
