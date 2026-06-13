import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.auth import CurrentUserInfo, get_current_user
from server.routers import projects


class _FakePM:
    def __init__(self, base: Path):
        self.base = base
        self.project_data = {
            "ready": {
                "title": "Ready",
                "style": "Anime",
                "episodes": [{"episode": 1, "script_file": "scripts/episode_1.json"}],
                "overview": {"synopsis": "old"},
            },
            "broken": {
                "title": "Broken",
                "style": "",
                "episodes": [],
            },
        }
        self.scripts = {
            ("ready", "episode_1.json"): {
                "content_mode": "drama",
                "scenes": [{"scene_id": "001", "duration_seconds": 8}],
            },
            ("ready", "narration.json"): {
                "content_mode": "narration",
                "segments": [{"segment_id": "E1S01", "duration_seconds": 4}],
            },
        }
        self.created = set()
        self.generated_names = ["project-aa11bb22", "project-cc33dd44"]
        (self.base / "ready" / "storyboards").mkdir(parents=True, exist_ok=True)
        (self.base / "ready" / "storyboards" / "scene_E1S01.png").write_bytes(b"png")
        (self.base / "empty").mkdir(parents=True, exist_ok=True)
        (self.base / "remove-me").mkdir(parents=True, exist_ok=True)

    def list_projects(self):
        return ["ready", "empty", "broken"]

    def project_exists(self, name):
        return name in {"ready", "broken"}

    def load_project(self, name):
        if name == "broken":
            raise RuntimeError("broken")
        if name not in self.project_data:
            raise FileNotFoundError(name)
        return self.project_data[name]

    def get_project_path(self, name):
        path = self.base / name
        if not path.exists():
            raise FileNotFoundError(name)
        return path

    def get_project_status(self, name):
        return {"current_stage": "source_ready"}

    def create_project(self, name):
        if not name or not re.fullmatch(r"[A-Za-z0-9-]+", name):
            raise ValueError("專案標識僅允許英文字母、數字和中劃線")
        if name == "exists":
            raise FileExistsError(name)
        self.created.add(name)
        (self.base / name).mkdir(parents=True, exist_ok=True)

    def generate_project_name(self, title):
        return self.generated_names.pop(0)

    def create_project_metadata(self, name, title, style, content_mode, aspect_ratio="9:16", default_duration=None):
        payload = {
            "title": (title or name),
            "style": style or "",
            "content_mode": content_mode,
            "aspect_ratio": aspect_ratio,
            "episodes": [],
        }
        if default_duration is not None:
            payload["default_duration"] = default_duration
        self.project_data[name] = payload
        return payload

    def save_project(self, name, payload):
        self.project_data[name] = payload

    def add_episode(self, project_name, episode, title, script_file):
        project = self.load_project(project_name)
        episodes = project.setdefault("episodes", [])
        episodes.append({"episode": episode, "title": title, "script_file": script_file})
        episodes.sort(key=lambda ep: ep["episode"])
        self.save_project(project_name, project)
        return project

    def remove_episode(self, project_name, episode):
        project = self.load_project(project_name)
        episodes = project.get("episodes", [])
        if not any(int(ep.get("episode", -1)) == int(episode) for ep in episodes):
            raise KeyError(f"劇集 E{episode} 不存在")
        removed = [f"scripts/episode_{episode}.json"]
        self.scripts.pop((project_name, f"episode_{episode}.json"), None)
        project["episodes"] = [ep for ep in episodes if int(ep.get("episode", -1)) != int(episode)]
        self.save_project(project_name, project)
        return project, removed

    def reorder_episodes(self, project_name, ordered_episode_numbers):
        project = self.load_project(project_name)
        episodes = project.get("episodes", [])
        existing = sorted(int(ep.get("episode", -1)) for ep in episodes)
        requested = [int(n) for n in ordered_episode_numbers]
        if existing != sorted(requested) or len(set(requested)) != len(requested):
            raise ValueError(f"集數不一致：現存 {existing}，傳入 {requested}")
        order_map = {ep_num: idx for idx, ep_num in enumerate(requested)}
        for ep in episodes:
            ep["order"] = order_map[int(ep["episode"])]
        self.save_project(project_name, project)
        return project

    def load_script(self, name, script_file):
        if script_file.startswith("scripts/"):
            script_file = script_file[len("scripts/") :]
        key = (name, script_file)
        if key not in self.scripts:
            raise FileNotFoundError(script_file)
        return self.scripts[key]

    def save_script(self, name, payload, script_file):
        self.scripts[(name, script_file)] = payload

    async def generate_overview(self, name, model=None, instruction=None):
        if name == "ready":
            return {"synopsis": "generated"}
        raise ValueError("source missing")


class _FakeCalc:
    def calculate_project_status(self, name, project):
        return {
            "current_phase": "storyboard",
            "phase_progress": 0.5,
            "characters": {"total": 1, "completed": 0},
            "clues": {"total": 1, "completed": 0},
            "scenes": {"total": 1, "completed": 0},
            "episodes_summary": {"total": 1, "scripted": 1, "in_production": 1, "completed": 0},
        }

    def enrich_project(self, name, project):
        project = dict(project)
        project["status"] = self.calculate_project_status(name, project)
        return project

    def enrich_script(self, script):
        script = dict(script)
        script["metadata"] = {"total_scenes": 1, "estimated_duration_seconds": 8}
        return script


def _client(monkeypatch, fake_pm, fake_calc):
    monkeypatch.setattr(projects, "get_project_manager", lambda: fake_pm)
    monkeypatch.setattr(projects, "get_status_calculator", lambda: fake_calc)

    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: CurrentUserInfo(id="default", sub="testuser", role="admin")
    app.include_router(projects.router, prefix="/api/v1")
    return TestClient(app)


class TestProjectsRouter:
    def test_list_and_create_and_delete(self, tmp_path, monkeypatch):
        client = _client(monkeypatch, _FakePM(tmp_path), _FakeCalc())
        with client:
            listed = client.get("/api/v1/projects")
            assert listed.status_code == 200
            names = [p["name"] for p in listed.json()["projects"]]
            assert names == ["ready", "empty", "broken"]
            broken = [p for p in listed.json()["projects"] if p["name"] == "broken"][0]
            assert broken["status"] == {}
            assert "error" in broken

            create_ok = client.post(
                "/api/v1/projects",
                json={"title": "New", "style": "Real", "content_mode": "narration"},
            )
            assert create_ok.status_code == 200
            assert create_ok.json()["name"] == "project-aa11bb22"
            assert create_ok.json()["project"]["title"] == "New"

            create_manual_name = client.post(
                "/api/v1/projects",
                json={"name": "manual-project", "style": "Anime", "content_mode": "narration"},
            )
            assert create_manual_name.status_code == 200
            assert create_manual_name.json()["name"] == "manual-project"
            assert create_manual_name.json()["project"]["title"] == "manual-project"

            create_exists = client.post(
                "/api/v1/projects",
                json={"name": "exists", "title": "Dup", "style": "", "content_mode": "narration"},
            )
            assert create_exists.status_code == 400

            create_invalid = client.post(
                "/api/v1/projects",
                json={"name": "bad_name", "title": "Bad", "style": "", "content_mode": "narration"},
            )
            assert create_invalid.status_code == 400

            create_missing_title = client.post(
                "/api/v1/projects",
                json={"style": "", "content_mode": "narration"},
            )
            assert create_missing_title.status_code == 400

            delete_ok = client.delete("/api/v1/projects/remove-me")
            assert delete_ok.status_code == 200

    def test_project_details_and_updates(self, tmp_path, monkeypatch):
        fake_pm = _FakePM(tmp_path)
        client = _client(monkeypatch, fake_pm, _FakeCalc())

        with client:
            detail = client.get("/api/v1/projects/ready")
            assert detail.status_code == 200
            assert "status" in detail.json()["project"]
            assert "episode_1.json" in detail.json()["scripts"]

            missing = client.get("/api/v1/projects/missing")
            assert missing.status_code == 404

            update = client.patch(
                "/api/v1/projects/ready",
                json={"title": "Updated", "style": "Noir"},
            )
            assert update.status_code == 200
            assert update.json()["project"]["title"] == "Updated"

            rejected_mode = client.patch(
                "/api/v1/projects/ready",
                json={"content_mode": "drama"},
            )
            assert rejected_mode.status_code == 400

            # aspect_ratio 現在允許修改（字串），dict 型別將被 Pydantic 拒絕（422）
            rejected_ratio_dict = client.patch(
                "/api/v1/projects/ready",
                json={"aspect_ratio": {"videos": "16:9"}},
            )
            assert rejected_ratio_dict.status_code == 422

            # aspect_ratio 字串更新應成功
            updated_ratio = client.patch(
                "/api/v1/projects/ready",
                json={"aspect_ratio": "16:9"},
            )
            assert updated_ratio.status_code == 200
            assert updated_ratio.json()["project"]["aspect_ratio"] == "16:9"

            updated_video_settings = client.patch(
                "/api/v1/projects/ready",
                json={"video_model_settings": {"veo-3.1-lite-generate-preview": {"resolution": "1080p"}}},
            )
            assert updated_video_settings.status_code == 200
            assert updated_video_settings.json()["project"]["video_model_settings"] == {
                "veo-3.1-lite-generate-preview": {"resolution": "1080p"}
            }

            get_script = client.get("/api/v1/projects/ready/scripts/episode_1.json")
            assert get_script.status_code == 200

            get_script_missing = client.get("/api/v1/projects/ready/scripts/missing.json")
            assert get_script_missing.status_code == 404

            create_episode = client.post("/api/v1/projects/ready/episodes", json={})
            assert create_episode.status_code == 200
            assert create_episode.json()["episode"] == {
                "episode": 2,
                "title": "第 2 集",
                "script_file": "scripts/episode_2.json",
            }
            assert fake_pm.project_data["ready"]["episodes"][-1]["episode"] == 2

            duplicate_episode = client.post("/api/v1/projects/ready/episodes", json={"episode": 1})
            assert duplicate_episode.status_code == 400

    def test_scene_segment_and_overview_endpoints(self, tmp_path, monkeypatch):
        fake_pm = _FakePM(tmp_path)
        fake_pm.scripts[("ready", "episode_1.json")] = {
            "content_mode": "drama",
            "scenes": [{"scene_id": "001", "duration_seconds": 8, "image_prompt": {}, "video_prompt": {}}],
        }
        fake_pm.scripts[("ready", "narration.json")] = {
            "content_mode": "narration",
            "segments": [{"segment_id": "E1S01", "duration_seconds": 4}],
        }

        client = _client(monkeypatch, fake_pm, _FakeCalc())

        with client:
            patch_scene = client.patch(
                "/api/v1/projects/ready/scenes/001",
                json={"script_file": "episode_1.json", "updates": {"duration_seconds": 6, "segment_break": True}},
            )
            assert patch_scene.status_code == 200
            assert patch_scene.json()["scene"]["duration_seconds"] == 6

            patch_scene_missing = client.patch(
                "/api/v1/projects/ready/scenes/404",
                json={"script_file": "episode_1.json", "updates": {}},
            )
            assert patch_scene_missing.status_code == 404

            patch_segment = client.patch(
                "/api/v1/projects/ready/segments/E1S01",
                json={
                    "script_file": "narration.json",
                    "duration_seconds": 8,
                    "segment_break": True,
                    "characters_in_segment": ["Hero"],
                    "clues_in_segment": ["Key"],
                },
            )
            assert patch_segment.status_code == 200
            assert patch_segment.json()["segment"]["characters_in_segment"] == ["Hero"]
            assert patch_segment.json()["segment"]["clues_in_segment"] == ["Key"]

            not_narration = client.patch(
                "/api/v1/projects/ready/segments/001",
                json={"script_file": "episode_1.json", "duration_seconds": 8},
            )
            assert not_narration.status_code == 400

            segment_missing = client.patch(
                "/api/v1/projects/ready/segments/E9S99",
                json={"script_file": "narration.json", "duration_seconds": 8},
            )
            assert segment_missing.status_code == 404

            gen_overview_ok = client.post("/api/v1/projects/ready/generate-overview")
            assert gen_overview_ok.status_code == 200

            gen_overview_bad = client.post("/api/v1/projects/bad/generate-overview")
            assert gen_overview_bad.status_code == 400

            update_overview = client.patch(
                "/api/v1/projects/ready/overview",
                json={"synopsis": "new synopsis", "genre": "懸疑", "theme": "真相", "world_setting": "古代"},
            )
            assert update_overview.status_code == 200
            assert update_overview.json()["overview"]["synopsis"] == "new synopsis"

    def test_get_project_includes_asset_fingerprints(self, tmp_path, monkeypatch):
        """專案 API 應返回 asset_fingerprints 欄位"""
        fake_pm = _FakePM(tmp_path)
        client = _client(monkeypatch, fake_pm, _FakeCalc())

        with client:
            resp = client.get("/api/v1/projects/ready")
            assert resp.status_code == 200
            data = resp.json()
            assert "asset_fingerprints" in data
            assert "storyboards/scene_E1S01.png" in data["asset_fingerprints"]
            assert isinstance(data["asset_fingerprints"]["storyboards/scene_E1S01.png"], int)

    def test_create_episode_writes_empty_skeleton(self, tmp_path, monkeypatch):
        fake_pm = _FakePM(tmp_path)
        client = _client(monkeypatch, fake_pm, _FakeCalc())
        with client:
            # ready 沒有 content_mode → 預設 narration
            resp = client.post("/api/v1/projects/ready/episodes", json={})
            assert resp.status_code == 200
            assert resp.json()["episode"]["episode"] == 2
            script = fake_pm.scripts[("ready", "episode_2.json")]
            assert script["content_mode"] == "narration"
            assert script["segments"] == []
            assert script["episode"] == 2

    def test_create_episode_drama_skeleton(self, tmp_path, monkeypatch):
        fake_pm = _FakePM(tmp_path)
        fake_pm.project_data["ready"]["content_mode"] = "drama"
        client = _client(monkeypatch, fake_pm, _FakeCalc())
        with client:
            resp = client.post("/api/v1/projects/ready/episodes", json={})
            assert resp.status_code == 200
            script = fake_pm.scripts[("ready", "episode_2.json")]
            assert script["content_mode"] == "drama"
            assert script["scenes"] == []

    def test_add_segment_and_scene_endpoints(self, tmp_path, monkeypatch):
        fake_pm = _FakePM(tmp_path)
        # ready/episode_1.json 預設是 drama；另設一個 narration 的劇集 2
        fake_pm.project_data["ready"]["episodes"].append({"episode": 2, "script_file": "scripts/episode_2.json"})
        fake_pm.scripts[("ready", "episode_2.json")] = {
            "episode": 2,
            "title": "第 2 集",
            "content_mode": "narration",
            "segments": [],
        }
        client = _client(monkeypatch, fake_pm, _FakeCalc())
        with client:
            # narration 劇集：新增片段
            r1 = client.post("/api/v1/projects/ready/episodes/2/segments")
            assert r1.status_code == 200
            assert r1.json()["segment"]["segment_id"] == "E2S1"
            assert r1.json()["segments_count"] == 1
            # 再加一個 → E2S2
            r2 = client.post("/api/v1/projects/ready/episodes/2/segments")
            assert r2.status_code == 200
            assert r2.json()["segment"]["segment_id"] == "E2S2"
            assert r2.json()["segments_count"] == 2

            # narration 模式呼叫 /scenes → 400（端點看 project 的 content_mode；ready 無設定 → 預設 narration）
            assert client.post("/api/v1/projects/ready/episodes/2/scenes").status_code == 400
            assert client.post("/api/v1/projects/ready/episodes/1/scenes").status_code == 400
            # 劇本不存在 → 404
            assert client.post("/api/v1/projects/ready/episodes/99/segments").status_code == 404
            # 專案不存在 → 404
            assert client.post("/api/v1/projects/nope/episodes/1/segments").status_code == 404

    def test_add_scene_drama_project(self, tmp_path, monkeypatch):
        fake_pm = _FakePM(tmp_path)
        fake_pm.project_data["ready"]["content_mode"] = "drama"
        fake_pm.scripts[("ready", "episode_1.json")] = {
            "episode": 1,
            "title": "第 1 集",
            "content_mode": "drama",
            "scenes": [],
        }
        client = _client(monkeypatch, fake_pm, _FakeCalc())
        with client:
            r = client.post("/api/v1/projects/ready/episodes/1/scenes")
            assert r.status_code == 200
            assert r.json()["scene"]["scene_id"] == "E1S1"
            assert r.json()["scenes_count"] == 1
            # drama 劇集呼叫 /segments → 400
            bad = client.post("/api/v1/projects/ready/episodes/1/segments")
            assert bad.status_code == 400

    def test_delete_episode_endpoint(self, tmp_path, monkeypatch):
        fake_pm = _FakePM(tmp_path)
        client = _client(monkeypatch, fake_pm, _FakeCalc())
        with client:
            r = client.delete("/api/v1/projects/ready/episodes/1")
            assert r.status_code == 200
            body = r.json()
            assert body["episode"] == 1
            assert "scripts/episode_1.json" in body["removed"]
            assert fake_pm.project_data["ready"]["episodes"] == []
            assert ("ready", "episode_1.json") not in fake_pm.scripts
            # 不存在的集數 → 404
            assert client.delete("/api/v1/projects/ready/episodes/99").status_code == 404
            # 不存在的專案 → 404
            assert client.delete("/api/v1/projects/nope/episodes/1").status_code == 404

    def test_reset_episode_script_endpoint(self, tmp_path, monkeypatch):
        fake_pm = _FakePM(tmp_path)
        client = _client(monkeypatch, fake_pm, _FakeCalc())
        with client:
            r = client.delete("/api/v1/projects/ready/episodes/1/script")
            assert r.status_code == 200
            assert r.json()["content_mode"] == "drama"
            reset = fake_pm.scripts[("ready", "episode_1.json")]
            assert reset["scenes"] == []
            assert reset["episode"] == 1
            assert client.delete("/api/v1/projects/ready/episodes/99/script").status_code == 404

    def test_delete_segment_and_scene_endpoints(self, tmp_path, monkeypatch):
        fake_pm = _FakePM(tmp_path)
        fake_pm.scripts[("ready", "narration.json")] = {
            "content_mode": "narration",
            "segments": [{"segment_id": "E1S01"}, {"segment_id": "E1S02"}],
        }
        client = _client(monkeypatch, fake_pm, _FakeCalc())
        with client:
            # 刪場景（drama，episode_1.json）
            r = client.delete("/api/v1/projects/ready/scenes/001", params={"script_file": "scripts/episode_1.json"})
            assert r.status_code == 200
            assert r.json()["scenes_count"] == 0
            assert fake_pm.scripts[("ready", "episode_1.json")]["scenes"] == []
            # 刪片段（narration）
            r2 = client.delete(
                "/api/v1/projects/ready/segments/E1S01", params={"script_file": "scripts/narration.json"}
            )
            assert r2.status_code == 200
            assert r2.json()["segments_count"] == 1
            assert [s["segment_id"] for s in fake_pm.scripts[("ready", "narration.json")]["segments"]] == ["E1S02"]
            # 找不到的 id → 404
            assert (
                client.delete(
                    "/api/v1/projects/ready/segments/nope", params={"script_file": "scripts/narration.json"}
                ).status_code
                == 404
            )
            # 缺 script_file → 422
            assert client.delete("/api/v1/projects/ready/segments/E1S02").status_code == 422

    def test_reorder_episodes_endpoint(self, tmp_path, monkeypatch):
        fake_pm = _FakePM(tmp_path)
        # 多加一集，方便排序
        fake_pm.project_data["ready"]["episodes"].append({"episode": 2, "script_file": "scripts/episode_2.json"})
        client = _client(monkeypatch, fake_pm, _FakeCalc())
        with client:
            r = client.patch(
                "/api/v1/projects/ready/episodes/order",
                json={"episodes": [2, 1]},
            )
            assert r.status_code == 200
            episodes = fake_pm.project_data["ready"]["episodes"]
            order_by_ep = {ep["episode"]: ep["order"] for ep in episodes}
            assert order_by_ep == {2: 0, 1: 1}
            # 集數不一致 → 409
            bad = client.patch(
                "/api/v1/projects/ready/episodes/order",
                json={"episodes": [1, 2, 99]},
            )
            assert bad.status_code == 409
            # 專案不存在 → 404
            assert (
                client.patch(
                    "/api/v1/projects/nope/episodes/order",
                    json={"episodes": [1]},
                ).status_code
                == 404
            )

    def test_preprocess_episode_source_not_ready_returns_400(self, tmp_path, monkeypatch):
        """尚未分集切分的集數按拆段 → SourceNotReadyError → HTTP 400（非 500）。"""
        import lib.episode_preprocess as ep

        def _raise(*args, **kwargs):
            raise ep.SourceNotReadyError("第 2 集尚未分集切分，請先切分後再執行拆段。")

        monkeypatch.setattr(ep, "run_preprocess", _raise)
        client = _client(monkeypatch, _FakePM(tmp_path), _FakeCalc())
        with client:
            r = client.post("/api/v1/projects/ready/episodes/2/preprocess")
            assert r.status_code == 400
            assert "分集切分" in r.json()["detail"]

    def test_preprocess_episode_runtime_error_still_500(self, tmp_path, monkeypatch):
        """非「尚未切分」的腳本失敗仍維持 HTTP 500。"""
        import lib.episode_preprocess as ep

        def _raise(*args, **kwargs):
            raise RuntimeError("split_narration_segments.py 失敗 (rc=1)")

        monkeypatch.setattr(ep, "run_preprocess", _raise)
        client = _client(monkeypatch, _FakePM(tmp_path), _FakeCalc())
        with client:
            r = client.post("/api/v1/projects/ready/episodes/2/preprocess")
            assert r.status_code == 500

    def test_get_source_paragraphs_endpoint(self, tmp_path, monkeypatch):
        """測試獲取 Step 1 原文段落的 API。"""
        fake_pm = _FakePM(tmp_path)
        client = _client(monkeypatch, fake_pm, _FakeCalc())

        # 建立假的專案草稿目錄 (ready 專案的實際路徑是 base / "ready")
        draft_dir = tmp_path / "ready" / "drafts" / "episode_1"
        draft_dir.mkdir(parents=True, exist_ok=True)

        # 寫入一個假表格
        draft_file = draft_dir / "step1_segments.md"
        draft_file.write_text(
            "| 片段 | 原文 | 字數 | 時長 |\n"
            "|------|------|------|------|\n"
            "| G01 | 這是第一段原文 | 7 | 4s |\n"
            "| G02 | 這是第二段原文 | 7 | 4s |\n",
            encoding="utf-8",
        )

        with client:
            # 專案不存在
            r_missing_project = client.get("/api/v1/projects/nope/episodes/1/source-paragraphs")
            assert r_missing_project.status_code == 404

            # 成功獲取段落
            r_ok = client.get("/api/v1/projects/ready/episodes/1/source-paragraphs")
            assert r_ok.status_code == 200
            paragraphs = r_ok.json()["paragraphs"]
            assert len(paragraphs) == 2
            assert paragraphs[0] == {"id": "G01", "content": "這是第一段原文"}
            assert paragraphs[1] == {"id": "G02", "content": "這是第二段原文"}

            # 草稿不存在，回傳空陣列
            r_no_draft = client.get("/api/v1/projects/ready/episodes/99/source-paragraphs")
            assert r_no_draft.status_code == 200
            assert r_no_draft.json()["paragraphs"] == []

    def test_preprocess_episode_with_source(self, tmp_path, monkeypatch):
        """測試 preprocess 路由能接收並傳遞可選的 source 欄位。"""
        import lib.episode_preprocess as ep

        captured_kwargs = {}

        def _mock_preprocess(*args, **kwargs):
            captured_kwargs.clear()
            captured_kwargs.update(kwargs)
            return {"step1_path": "drafts/episode_2/step1_segments.md", "content_mode": "narration"}

        monkeypatch.setattr(ep, "run_preprocess", _mock_preprocess)
        client = _client(monkeypatch, _FakePM(tmp_path), _FakeCalc())
        with client:
            # 傳遞 json 帶有 source
            r = client.post("/api/v1/projects/ready/episodes/2/preprocess", json={"source": "source/custom.txt"})
            assert r.status_code == 200
            assert captured_kwargs.get("source") == "source/custom.txt"

            # 不傳 body 也要能相容
            r_empty = client.post("/api/v1/projects/ready/episodes/2/preprocess")
            assert r_empty.status_code == 200
            assert captured_kwargs.get("source") is None

    def test_preprocess_episode_num_segments_validation(self, tmp_path, monkeypatch):
        """測試 num_segments 只接受 1 到 100 的整數。"""
        import lib.episode_preprocess as ep

        def _mock_preprocess(*args, **kwargs):
            return {"step1_path": "...", "content_mode": "narration"}

        monkeypatch.setattr(ep, "run_preprocess", _mock_preprocess)
        client = _client(monkeypatch, _FakePM(tmp_path), _FakeCalc())
        with client:
            for num_segments in (0, 101):
                r = client.post(
                    "/api/v1/projects/ready/episodes/2/preprocess",
                    json={"num_segments": num_segments},
                )
                assert r.status_code == 422

            r = client.post("/api/v1/projects/ready/episodes/2/preprocess", json={"num_segments": 10})
            assert r.status_code == 200

    def test_compose_episode_sets_pythonpath_for_skill_script(self, tmp_path, monkeypatch):
        fake_pm = _FakePM(tmp_path)
        project_dir = fake_pm.get_project_path("ready")
        (project_dir / "scripts").mkdir(parents=True, exist_ok=True)
        (project_dir / "scripts" / "episode_1.json").write_text("{}", encoding="utf-8")
        captured = {}

        def fake_run(cmd, *, cwd, capture_output, text, timeout, env):
            captured["cmd"] = cmd
            captured["cwd"] = cwd
            captured["env"] = env
            return SimpleNamespace(returncode=0, stdout="✅ 影片合成完成: output/episode_1_final.mp4\n", stderr="")

        monkeypatch.setattr("subprocess.run", fake_run)
        client = _client(monkeypatch, fake_pm, _FakeCalc())
        with client:
            r = client.post("/api/v1/projects/ready/episodes/1/compose")

        assert r.status_code == 200
        assert captured["cmd"][0] == sys.executable
        assert captured["cmd"][-2:] == ["--output", "episode_1_final.mp4"]
        assert captured["cwd"] == str(project_dir)
        pythonpath_entries = captured["env"]["PYTHONPATH"].split(os.pathsep)
        assert str(projects.PROJECT_ROOT) in pythonpath_entries

    def test_compose_episode_creates_output_version_with_source_clips(self, tmp_path, monkeypatch):
        fake_pm = _FakePM(tmp_path)
        fake_pm.scripts[("ready", "episode_1.json")] = {
            "content_mode": "narration",
            "segments": [
                {"segment_id": "E1S01", "generated_assets": {"video_clip": "videos/scene_E1S01.mp4"}},
                {"segment_id": "E1S02", "generated_assets": {"video_clip": "videos/scene_E1S02.mp4"}},
            ],
        }
        project_dir = fake_pm.get_project_path("ready")
        (project_dir / "scripts").mkdir(parents=True, exist_ok=True)
        (project_dir / "scripts" / "episode_1.json").write_text(
            '{"content_mode":"narration","segments":[{"segment_id":"E1S01","generated_assets":{"video_clip":"videos/scene_E1S01.mp4"}},{"segment_id":"E1S02","generated_assets":{"video_clip":"videos/scene_E1S02.mp4"}}]}',
            encoding="utf-8",
        )
        (project_dir / "output").mkdir(parents=True, exist_ok=True)

        def fake_run(cmd, *, cwd, capture_output, text, timeout, env):
            (Path(cwd) / "output" / "episode_1_final.mp4").write_bytes(b"final")
            return SimpleNamespace(returncode=0, stdout="✅ 影片合成完成: output/episode_1_final.mp4\n", stderr="")

        monkeypatch.setattr("subprocess.run", fake_run)
        client = _client(monkeypatch, fake_pm, _FakeCalc())
        with client:
            r = client.post("/api/v1/projects/ready/episodes/1/compose")

        assert r.status_code == 200
        payload = r.json()
        assert payload["version"] == 1
        versions_file = project_dir / "versions" / "versions.json"
        versions = json.loads(versions_file.read_text(encoding="utf-8"))
        record = versions["output"]["1"]["versions"][0]
        assert record["source_clips"] == ["videos/scene_E1S01.mp4", "videos/scene_E1S02.mp4"]
        assert record["file"].startswith("versions/output/1_v1_")
        assert record["file"].endswith(".mp4")

    def test_compose_episode_missing_video_returns_actionable_400(self, tmp_path, monkeypatch):
        fake_pm = _FakePM(tmp_path)
        project_dir = fake_pm.get_project_path("ready")
        (project_dir / "scripts").mkdir(parents=True, exist_ok=True)
        (project_dir / "scripts" / "episode_1.json").write_text("{}", encoding="utf-8")

        def fake_run(*args, **kwargs):
            return SimpleNamespace(returncode=1, stdout="❌ 錯誤: 場景 E1S2 缺少影片片段\n", stderr="")

        monkeypatch.setattr("subprocess.run", fake_run)
        client = _client(monkeypatch, fake_pm, _FakeCalc())
        with client:
            r = client.post("/api/v1/projects/ready/episodes/1/compose")

        assert r.status_code == 400
        assert r.json()["detail"] == "場景 E1S2 缺少影片片段，請先生成影片後再合成成片。"
