from fastapi import FastAPI
from fastapi.testclient import TestClient

from lib.project_manager import ProjectManager
from server.auth import CurrentUserInfo, get_current_user
from server.routers import projects, scenes


def _client(monkeypatch, tmp_path):
    pm = ProjectManager(tmp_path / "projects")
    pm.create_project("demo")
    pm.create_project_metadata("demo", "Demo", "Anime", "narration")
    pm.add_project_scene("demo", "天安門", "原描述")

    monkeypatch.setattr(projects, "get_project_manager", lambda: pm)
    monkeypatch.setattr(scenes, "get_project_manager", lambda: pm)

    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: CurrentUserInfo(id="default", sub="testuser", role="admin")
    app.include_router(projects.router, prefix="/api/v1")
    app.include_router(scenes.router, prefix="/api/v1")
    return TestClient(app), pm


def test_project_scene_patch_does_not_conflict_with_episode_scene_route(tmp_path, monkeypatch):
    client, pm = _client(monkeypatch, tmp_path)

    with client:
        response = client.patch(
            "/api/v1/projects/demo/project-scenes/%E5%A4%A9%E5%AE%89%E9%96%80",
            json={"description": "新描述"},
        )

    assert response.status_code == 200
    assert response.json()["scene"]["description"] == "新描述"
    assert pm.get_project_scene("demo", "天安門")["description"] == "新描述"


def test_project_scene_rename_updates_project_scene_key(tmp_path, monkeypatch):
    client, pm = _client(monkeypatch, tmp_path)

    with client:
        response = client.post(
            "/api/v1/projects/demo/project-scenes/%E5%A4%A9%E5%AE%89%E9%96%80/rename",
            json={"new_name": "中山樓"},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["old_name"] == "天安門"
    assert body["new_name"] == "中山樓"
    assert pm.get_project_scene("demo", "中山樓")["description"] == "原描述"


def test_update_segment_accepts_project_scene_reference(tmp_path, monkeypatch):
    client, pm = _client(monkeypatch, tmp_path)
    pm.save_script(
        "demo",
        {
            "episode": 1,
            "title": "第一集",
            "content_mode": "narration",
            "novel": {"title": "Demo", "chapter": "第一章"},
            "segments": [
                {
                    "segment_id": "SEG-1",
                    "duration_seconds": 4,
                    "segment_break": False,
                    "novel_text": "原文",
                    "characters_in_segment": [],
                    "clues_in_segment": [],
                    "scene_in_segment": None,
                    "image_prompt": "image",
                    "video_prompt": "video",
                    "transition_to_next": "cut",
                }
            ],
        },
        "episode_1.json",
    )

    with client:
        response = client.patch(
            "/api/v1/projects/demo/segments/SEG-1",
            json={
                "script_file": "episode_1.json",
                "scene_in_segment": "天安門",
            },
        )

    assert response.status_code == 200, response.text
    script = pm.load_script("demo", "episode_1.json")
    assert script["segments"][0]["scene_in_segment"] == "天安門"


def test_update_scene_accepts_project_scene_reference(tmp_path, monkeypatch):
    client, pm = _client(monkeypatch, tmp_path)
    pm.save_script(
        "demo",
        {
            "episode": 1,
            "title": "第一集",
            "content_mode": "drama",
            "novel": {"title": "Demo", "chapter": "第一章"},
            "scenes": [
                {
                    "scene_id": "SC-1",
                    "duration_seconds": 8,
                    "segment_break": False,
                    "scene_type": "劇情",
                    "characters_in_scene": [],
                    "clues_in_scene": [],
                    "scene_in_scene": None,
                    "image_prompt": "image",
                    "video_prompt": "video",
                    "transition_to_next": "cut",
                }
            ],
        },
        "episode_1.json",
    )

    with client:
        response = client.patch(
            "/api/v1/projects/demo/scenes/SC-1",
            json={
                "script_file": "episode_1.json",
                "updates": {"scene_in_scene": "天安門"},
            },
        )

    assert response.status_code == 200, response.text
    script = pm.load_script("demo", "episode_1.json")
    assert script["scenes"][0]["scene_in_scene"] == "天安門"


def test_batch_add_scenes(tmp_path, monkeypatch):
    client, pm = _client(monkeypatch, tmp_path)

    with client:
        response = client.post(
            "/api/v1/projects/demo/project-scenes/batch_create",
            json={
                "items": [{"name": "大雄寶殿", "description": "莊嚴 1"}, {"name": "藏經閣", "description": "幽暗 2"}]
            },
        )

    assert response.status_code == 200, response.text
    scenes = response.json()["scenes"]
    assert scenes["大雄寶殿"]["description"] == "莊嚴 1"
    assert scenes["藏經閣"]["description"] == "幽暗 2"
