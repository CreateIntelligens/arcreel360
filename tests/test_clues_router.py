from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.auth import CurrentUserInfo, get_current_user
from server.routers import clues


class _FakePM:
    def __init__(self):
        self.projects = {
            "demo": {
                "clues": {
                    "玉佩": {
                        "description": "old",
                        "importance": "major",
                        "clue_sheet": "",
                    }
                }
            }
        }

    def add_clue(self, project_name, name, description, importance):
        if project_name not in self.projects:
            raise FileNotFoundError(project_name)
        self.projects[project_name]["clues"][name] = {
            "description": description,
            "importance": importance,
        }
        return self.projects[project_name]

    def load_project(self, project_name):
        if project_name not in self.projects:
            raise FileNotFoundError(project_name)
        return self.projects[project_name]

    def save_project(self, project_name, project):
        self.projects[project_name] = project

    def update_project(self, project_name, mutate_fn):
        project = self.load_project(project_name)
        mutate_fn(project)
        self.save_project(project_name, project)


def _client(monkeypatch, fake_pm):
    monkeypatch.setattr(clues, "get_project_manager", lambda: fake_pm)
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: CurrentUserInfo(id="default", sub="testuser", role="admin")
    app.include_router(clues.router, prefix="/api/v1")
    return TestClient(app)


class TestCluesRouter:
    def test_add_update_delete(self, monkeypatch):
        fake_pm = _FakePM()
        with _client(monkeypatch, fake_pm) as client:
            add_resp = client.post(
                "/api/v1/projects/demo/clues",
                json={"name": "懷錶", "description": "陰森", "importance": "major"},
            )
            assert add_resp.status_code == 200
            assert add_resp.json()["clue"]["description"] == "陰森"

            patch_resp = client.patch(
                "/api/v1/projects/demo/clues/玉佩",
                json={"description": "new", "importance": "minor", "clue_sheet": "clues/a.png"},
            )
            assert patch_resp.status_code == 200
            assert patch_resp.json()["clue"]["importance"] == "minor"

            delete_resp = client.delete("/api/v1/projects/demo/clues/懷錶")
            assert delete_resp.status_code == 200

    def test_error_mapping(self, monkeypatch):
        fake_pm = _FakePM()
        with _client(monkeypatch, fake_pm) as client:
            missing = client.patch(
                "/api/v1/projects/demo/clues/missing",
                json={"description": "x"},
            )
            assert missing.status_code == 404

            bad_importance = client.patch(
                "/api/v1/projects/demo/clues/玉佩",
                json={"importance": "bad"},
            )
            assert bad_importance.status_code == 400

    def test_batch_add_clues(self, monkeypatch):
        fake_pm = _FakePM()
        with _client(monkeypatch, fake_pm) as client:
            resp = client.post(
                "/api/v1/projects/demo/clues/batch_create",
                json={
                    "items": [
                        {"name": "懷錶", "description": "陰森 1", "importance": "major"},
                        {"name": "玉石", "description": "溫潤 2", "importance": "minor"},
                    ]
                },
            )
            assert resp.status_code == 200
            clues = resp.json()["clues"]
            assert clues["懷錶"]["description"] == "陰森 1"
            assert clues["玉石"]["description"] == "溫潤 2"
