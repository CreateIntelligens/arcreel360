from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from lib.project_manager import ProjectManager
from server.auth import CurrentUserInfo, get_current_user
from server.routers import projects


class _FakeCalc:
    def enrich_project(self, name, project):
        return project


def _client(monkeypatch, pm: ProjectManager) -> TestClient:
    monkeypatch.setattr(projects, "get_project_manager", lambda: pm)
    monkeypatch.setattr(projects, "get_status_calculator", lambda: _FakeCalc())
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: CurrentUserInfo(id="default", sub="testuser", role="admin")
    app.include_router(projects.router, prefix="/api/v1")
    return TestClient(app)


def _setup_project(tmp_path):
    pm = ProjectManager(projects_root=tmp_path / "projects")
    pm.create_project("demo")
    pm.create_project_metadata("demo", title="Demo", style="anime", content_mode="narration")
    project_dir = pm.get_project_path("demo")
    (project_dir / "source").mkdir(parents=True, exist_ok=True)
    return pm, project_dir


def test_peek_endpoint_success(tmp_path, monkeypatch):
    pm, project_dir = _setup_project(tmp_path)
    (project_dir / "source" / "n.txt").write_text("甲" * 30 + "。" + "乙" * 30, encoding="utf-8")
    client = _client(monkeypatch, pm)

    with client:
        resp = client.post(
            "/api/v1/projects/demo/episodes/peek",
            json={"source": "source/n.txt", "target_chars": 20},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_chars"] == 61
    assert "nearby_breakpoints" in body


def test_peek_endpoint_target_overflow_422(tmp_path, monkeypatch):
    pm, project_dir = _setup_project(tmp_path)
    (project_dir / "source" / "n.txt").write_text("短文", encoding="utf-8")
    client = _client(monkeypatch, pm)

    with client:
        resp = client.post(
            "/api/v1/projects/demo/episodes/peek",
            json={"source": "source/n.txt", "target_chars": 100},
        )

    assert resp.status_code == 422


def test_split_endpoint_success_persisted(tmp_path, monkeypatch):
    pm, project_dir = _setup_project(tmp_path)
    (project_dir / "source" / "n.txt").write_text("前半段。他離開了。後半段。", encoding="utf-8")
    client = _client(monkeypatch, pm)

    with client:
        resp = client.post(
            "/api/v1/projects/demo/episodes/split",
            json={
                "source": "source/n.txt",
                "episode": 1,
                "target_chars": 5,
                "anchor": "他離開了。",
                "title": "第一集",
            },
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["episode"] == 1
    assert (project_dir / "source" / "episode_1.txt").exists()
    assert (project_dir / "source" / "_remaining.txt").exists()
    assert any(ep["episode"] == 1 and ep.get("title") == "第一集" for ep in pm.load_project("demo")["episodes"])


def test_split_endpoint_anchor_not_found_400(tmp_path, monkeypatch):
    pm, project_dir = _setup_project(tmp_path)
    (project_dir / "source" / "n.txt").write_text("一些內容。", encoding="utf-8")
    client = _client(monkeypatch, pm)

    with client:
        resp = client.post(
            "/api/v1/projects/demo/episodes/split",
            json={"source": "source/n.txt", "episode": 1, "target_chars": 2, "anchor": "不存在"},
        )

    assert resp.status_code == 400


def test_split_endpoint_rejects_path_escape_422(tmp_path, monkeypatch):
    pm, _project_dir = _setup_project(tmp_path)
    client = _client(monkeypatch, pm)

    with client:
        resp = client.post(
            "/api/v1/projects/demo/episodes/split",
            json={"source": "../../etc/passwd", "episode": 1, "target_chars": 2, "anchor": "x"},
        )

    assert resp.status_code == 422
