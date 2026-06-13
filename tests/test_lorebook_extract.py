from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.auth import CurrentUserInfo, get_current_user
from server.routers import projects


class _FakePM:
    def __init__(self):
        self.projects = {
            "demo": {
                "overview": {"synopsis": "這是一個故事", "genre": "科幻", "theme": "探索", "world_setting": "宇宙"}
            }
        }

    def _read_source_files(self, name, max_chars):
        return "小說原文片段"

    def load_project(self, project_name):
        return self.projects[project_name]


@pytest.mark.asyncio
async def test_lorebook_extract_characters(monkeypatch):
    fake_pm = _FakePM()
    monkeypatch.setattr(projects, "get_project_manager", lambda: fake_pm)

    # Mock TextGenerator
    mock_generator = AsyncMock()
    mock_result = AsyncMock()
    # Mock TextGenerator.generate 傳回包含 JSON 的 TextGenerationResult
    mock_result.text = '{"characters": [{"name": "阿福", "description": "老管家", "voice_style": "沉穩"}]}'
    mock_generator.generate.return_value = mock_result

    # Mock TextGenerator.create / create_with_model_str
    monkeypatch.setattr("lib.text_generator.TextGenerator.create", AsyncMock(return_value=mock_generator))
    monkeypatch.setattr(
        "lib.text_generator.TextGenerator.create_with_model_str", AsyncMock(return_value=mock_generator)
    )

    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: CurrentUserInfo(id="default", sub="testuser", role="admin")
    app.include_router(projects.router, prefix="/api/v1")

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/projects/demo/lorebook/extract",
            json={"model": "openai/gpt-4o", "entity_type": "character", "instruction": "撈出所有管家"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert len(data["characters"]) == 1
        assert data["characters"][0]["name"] == "阿福"
