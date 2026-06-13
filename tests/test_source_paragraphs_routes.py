from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from lib.project_manager import ProjectManager
from server.auth import CurrentUserInfo, get_current_user
from server.routers import project_episodes, projects

REAL_NARRATION_MD = (
    "## 片段拆分結果\n\n"
    "| 片段 | 原文 | 字數 | 時長 | 有對話 | segment_break |\n"
    "|------|------|------|------|--------|---------------|\n"
    "| G01 | 第一段原文。 | 6 | 4s | 否 | - |\n"
    "| G02 | 第二段原文。 | 6 | 8s | 是 | - |\n"
)


class _FakeCalc:
    def enrich_project(self, name, project):
        return project


def _client(monkeypatch, pm: ProjectManager) -> TestClient:
    monkeypatch.setattr(projects, "get_project_manager", lambda: pm)
    monkeypatch.setattr(projects, "get_status_calculator", lambda: _FakeCalc())
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: CurrentUserInfo(id="default", sub="testuser", role="admin")
    app.include_router(project_episodes.router, prefix="/api/v1")
    return TestClient(app)


def _setup_project(tmp_path):
    pm = ProjectManager(projects_root=tmp_path / "projects")
    pm.create_project("demo")
    pm.create_project_metadata("demo", title="Demo", style="anime", content_mode="narration")
    project_dir = pm.get_project_path("demo")
    draft_dir = project_dir / "drafts" / "episode_1"
    draft_dir.mkdir(parents=True, exist_ok=True)
    (draft_dir / "step1_segments.md").write_text(REAL_NARRATION_MD, encoding="utf-8")
    return pm, project_dir


def test_get_source_paragraphs_returns_id_and_content(tmp_path, monkeypatch):
    pm, _ = _setup_project(tmp_path)
    client = _client(monkeypatch, pm)
    with client:
        resp = client.get("/api/v1/projects/demo/episodes/1/source-paragraphs")
    assert resp.status_code == 200, resp.text
    paragraphs = resp.json()["paragraphs"]
    assert paragraphs == [
        {"id": "G01", "content": "第一段原文。"},
        {"id": "G02", "content": "第二段原文。"},
    ]


def test_update_source_paragraph_preserves_columns(tmp_path, monkeypatch):
    pm, project_dir = _setup_project(tmp_path)
    client = _client(monkeypatch, pm)
    with client:
        resp = client.put(
            "/api/v1/projects/demo/episodes/1/source-paragraphs/G01",
            json={"content": "改寫後的第一段"},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"success": True, "id": "G01", "content": "改寫後的第一段"}

    md = (project_dir / "drafts" / "episode_1" / "step1_segments.md").read_text(encoding="utf-8")
    assert "改寫後的第一段" in md
    assert "有對話" in md  # 欄位未被丟棄
    assert "| G02 | 第二段原文。 | 6 | 8s | 是 | - |" in md  # 未改列逐字保留


def test_update_source_paragraph_syncs_script_json(tmp_path, monkeypatch):
    pm, project_dir = _setup_project(tmp_path)
    script = {
        "content_mode": "narration",
        "segments": [
            {"segment_id": "G01", "novel_text": "第一段原文。"},
            {"segment_id": "G02", "novel_text": "第二段原文。"},
        ],
    }
    scripts_dir = project_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "episode_1.json").write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")

    client = _client(monkeypatch, pm)
    with client:
        resp = client.put(
            "/api/v1/projects/demo/episodes/1/source-paragraphs/G01",
            json={"content": "同步後的第一段"},
        )
    assert resp.status_code == 200, resp.text

    updated = json.loads((scripts_dir / "episode_1.json").read_text(encoding="utf-8"))
    assert updated["segments"][0]["novel_text"] == "同步後的第一段"
    assert updated["segments"][1]["novel_text"] == "第二段原文。"


def test_update_missing_segment_returns_404(tmp_path, monkeypatch):
    pm, _ = _setup_project(tmp_path)
    client = _client(monkeypatch, pm)
    with client:
        resp = client.put(
            "/api/v1/projects/demo/episodes/1/source-paragraphs/G99",
            json={"content": "x"},
        )
    assert resp.status_code == 404


def test_update_without_preprocess_returns_404(tmp_path, monkeypatch):
    pm = ProjectManager(projects_root=tmp_path / "projects")
    pm.create_project("demo")
    pm.create_project_metadata("demo", title="Demo", style="anime", content_mode="narration")
    client = _client(monkeypatch, pm)
    with client:
        resp = client.put(
            "/api/v1/projects/demo/episodes/1/source-paragraphs/G01",
            json={"content": "x"},
        )
    assert resp.status_code == 404
