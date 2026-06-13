"""批次生成與劇集流程 endpoint 的 happy path 測試。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.auth import CurrentUserInfo, get_current_user
from server.routers import generate, projects

# -------------------- 共用 Fakes --------------------


class _FakeQueue:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def enqueue_task(self, **kwargs):
        self.calls.append(kwargs)
        return {"task_id": f"task-{len(self.calls)}", "deduped": False}


class _FakePMGen:
    def __init__(self, project_path: Path) -> None:
        self.project_path = project_path
        self.project = {
            "characters": {
                "Alice": {"description": "hero"},
                "Bob": {"description": "side", "character_sheet": "characters/Bob.png"},
            },
            "clues": {
                "玉佩": {"type": "prop", "description": "綠色玉佩"},
                "古劍": {"type": "weapon", "description": "古劍", "clue_sheet": "clues/古劍.png"},
            },
            "scenes": {
                "古城": {"description": "斑駁城牆與夕陽"},
                "已生成場景": {"description": "舊場景", "scene_sheet": "scenes/已生成場景.png"},
            },
        }
        self.script = {
            "content_mode": "narration",
            "segments": [
                {"segment_id": "E1S01", "duration_seconds": 4},
                {"segment_id": "E1S02", "duration_seconds": 4},
                {"segment_id": "E1S03", "duration_seconds": 4},
            ],
        }

    def load_project(self, name):
        return self.project

    def get_project_path(self, name):
        return self.project_path

    def load_script(self, name, script_file):
        return self.script


def _client_gen(monkeypatch, fake_pm, fake_queue):
    monkeypatch.setattr(generate, "get_project_manager", lambda: fake_pm)
    monkeypatch.setattr(generate, "get_generation_queue", lambda: fake_queue)
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: CurrentUserInfo(id="default", sub="testuser", role="admin")
    app.include_router(generate.router, prefix="/api/v1")
    return TestClient(app)


def _prepare_project(tmp_path: Path) -> Path:
    p = tmp_path / "projects" / "demo"
    (p / "storyboards").mkdir(parents=True, exist_ok=True)
    (p / "videos").mkdir(parents=True, exist_ok=True)
    # E1S01 has storyboard already (skip in storyboard batch unless force)
    (p / "storyboards" / "scene_E1S01.png").write_bytes(b"png")
    # E1S02 has both storyboard and video already
    (p / "storyboards" / "scene_E1S02.png").write_bytes(b"png")
    (p / "videos" / "scene_E1S02.mp4").write_bytes(b"mp4")
    return p


class TestBatchGenerate:
    def test_storyboards_batch_skips_existing(self, tmp_path, monkeypatch):
        ppath = _prepare_project(tmp_path)
        pm = _FakePMGen(ppath)
        queue = _FakeQueue()
        client = _client_gen(monkeypatch, pm, queue)

        with client:
            resp = client.post(
                "/api/v1/projects/demo/generate/storyboards/batch",
                json={"script_file": "episode_1.json"},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # E1S01, E1S02 already have storyboards → skipped; E1S03 enqueued
        assert "E1S03" in body["enqueued"]
        assert any(s["id"] == "E1S01" and s["reason"] == "already_exists" for s in body["skipped"])
        assert len(queue.calls) == 1

    def test_storyboards_batch_force_enqueues_all(self, tmp_path, monkeypatch):
        ppath = _prepare_project(tmp_path)
        pm = _FakePMGen(ppath)
        queue = _FakeQueue()
        client = _client_gen(monkeypatch, pm, queue)

        with client:
            resp = client.post(
                "/api/v1/projects/demo/generate/storyboards/batch",
                json={"script_file": "episode_1.json", "force": True},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert set(body["enqueued"]) == {"E1S01", "E1S02", "E1S03"}
        assert len(queue.calls) == 3

    def test_videos_batch_requires_storyboards(self, tmp_path, monkeypatch):
        ppath = _prepare_project(tmp_path)
        pm = _FakePMGen(ppath)
        queue = _FakeQueue()
        client = _client_gen(monkeypatch, pm, queue)

        with client:
            resp = client.post(
                "/api/v1/projects/demo/generate/videos/batch",
                json={"script_file": "episode_1.json"},
            )
        assert resp.status_code == 200
        body = resp.json()
        # E1S01 has storyboard but no video → enqueued
        # E1S02 has both → skipped already_exists
        # E1S03 has no storyboard → skipped missing_storyboard
        assert body["enqueued"] == ["E1S01"]
        reasons = {s["id"]: s["reason"] for s in body["skipped"]}
        assert reasons.get("E1S02") == "already_exists"
        assert reasons.get("E1S03") == "missing_storyboard"

    def test_characters_batch(self, tmp_path, monkeypatch):
        ppath = _prepare_project(tmp_path)
        pm = _FakePMGen(ppath)
        queue = _FakeQueue()
        client = _client_gen(monkeypatch, pm, queue)

        with client:
            resp = client.post("/api/v1/projects/demo/generate/characters/batch", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body["enqueued"] == ["Alice"]
        assert any(s["id"] == "Bob" and s["reason"] == "already_exists" for s in body["skipped"])

    def test_clues_batch_with_explicit_names(self, tmp_path, monkeypatch):
        ppath = _prepare_project(tmp_path)
        pm = _FakePMGen(ppath)
        queue = _FakeQueue()
        client = _client_gen(monkeypatch, pm, queue)

        with client:
            resp = client.post(
                "/api/v1/projects/demo/generate/clues/batch",
                json={"names": ["玉佩", "未知"]},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["enqueued"] == ["玉佩"]
        reasons = {s["id"]: s["reason"] for s in body["skipped"]}
        assert reasons.get("未知") == "not_found"

    def test_generate_scene(self, tmp_path, monkeypatch):
        ppath = _prepare_project(tmp_path)
        pm = _FakePMGen(ppath)
        queue = _FakeQueue()
        client = _client_gen(monkeypatch, pm, queue)

        with client:
            resp = client.post(
                "/api/v1/projects/demo/generate/scene/古城",
                json={"prompt": "斑駁城牆與夕陽"},
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        assert body["task_id"] == "task-1"
        assert len(queue.calls) == 1
        assert queue.calls[0]["task_type"] == "scene"
        assert queue.calls[0]["media_type"] == "image"
        assert queue.calls[0]["resource_id"] == "古城"
        assert queue.calls[0]["payload"]["prompt"] == "斑駁城牆與夕陽"

    def test_scenes_batch_with_explicit_names(self, tmp_path, monkeypatch):
        ppath = _prepare_project(tmp_path)
        pm = _FakePMGen(ppath)
        queue = _FakeQueue()
        client = _client_gen(monkeypatch, pm, queue)

        with client:
            resp = client.post(
                "/api/v1/projects/demo/generate/scenes/batch",
                json={"names": ["古城", "未知"]},
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["enqueued"] == ["古城"]
        reasons = {s["id"]: s["reason"] for s in body["skipped"]}
        assert reasons.get("未知") == "not_found"
        assert len(queue.calls) == 1
        assert queue.calls[0]["task_type"] == "scene"
        assert queue.calls[0]["media_type"] == "image"
        assert queue.calls[0]["resource_id"] == "古城"
        assert queue.calls[0]["payload"]["prompt"] == "斑駁城牆與夕陽"
        assert queue.calls[0]["payload"]["from_batch"] is True


# -------------------- 劇集流程：compose / script / preprocess --------------------


class _FakePMProj:
    def __init__(self, base: Path, content_mode: str = "drama") -> None:
        self.base = base
        self.content_mode = content_mode
        (base / "demo" / "scripts").mkdir(parents=True, exist_ok=True)
        (base / "demo" / "scripts" / "episode_1.json").write_text("{}", encoding="utf-8")
        self.project = {
            "title": "Demo",
            "content_mode": content_mode,
            "episodes": [{"episode": 1, "script_file": "scripts/episode_1.json"}],
        }
        self.saved: dict | None = None

    def project_exists(self, name):
        return name == "demo"

    def load_project(self, name):
        if name != "demo":
            raise FileNotFoundError(name)
        return self.project

    def get_project_path(self, name):
        return self.base / name

    def save_project(self, name, payload):
        self.saved = payload
        self.project = payload

    def load_script(self, name, script_file):
        return {"content_mode": "drama", "scenes": [{"scene_id": "E1S01"}]}


class _FakeCalc:
    def calculate_project_status(self, name, project):
        return {}

    def enrich_project(self, name, project):
        return project

    def enrich_script(self, script):
        return script


def _client_proj(monkeypatch, fake_pm):
    monkeypatch.setattr(projects, "get_project_manager", lambda: fake_pm)
    monkeypatch.setattr(projects, "get_status_calculator", lambda: _FakeCalc())
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: CurrentUserInfo(id="default", sub="testuser", role="admin")
    app.include_router(projects.router, prefix="/api/v1")
    return TestClient(app)


class _FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestEpisodeFlow:
    def test_compose_happy_path(self, tmp_path, monkeypatch):
        pm = _FakePMProj(tmp_path)
        # Pre-create output dir & file so fallback finds it
        out = tmp_path / "demo" / "output"
        out.mkdir(parents=True, exist_ok=True)
        (out / "episode_1_final.mp4").write_bytes(b"mp4")

        def fake_run(*args, **kwargs):
            return _FakeProc(
                returncode=0,
                stdout="🎬 開始合成\n✅ 影片合成完成: output/episode_1_final.mp4\n",
            )

        # subprocess is imported inside the function; patch the global module
        import subprocess

        monkeypatch.setattr(subprocess, "run", fake_run)
        client = _client_proj(monkeypatch, pm)

        with client:
            resp = client.post("/api/v1/projects/demo/episodes/1/compose")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "episode_1_final.mp4" in body["output_path"]
        assert "duration_seconds" in body

    def test_compose_404_when_episode_missing(self, tmp_path, monkeypatch):
        pm = _FakePMProj(tmp_path)
        client = _client_proj(monkeypatch, pm)
        with client:
            resp = client.post("/api/v1/projects/demo/episodes/99/compose")
        assert resp.status_code == 404

    def test_script_endpoint_happy_path(self, tmp_path, monkeypatch):
        pm = _FakePMProj(tmp_path)

        # Stub ScriptGenerator
        class _FakeGen:
            @classmethod
            async def create(cls, project_path):
                return cls()

            async def generate(
                self,
                episode,
                output_path=None,
                extra_instruction=None,
            ):
                out = pm.base / "demo" / "scripts" / f"episode_{episode}.json"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text('{"segments": [{}, {}]}', encoding="utf-8")
                return out

        import lib.script_generator as sg

        monkeypatch.setattr(sg, "ScriptGenerator", _FakeGen)
        client = _client_proj(monkeypatch, pm)

        with client:
            resp = client.post("/api/v1/projects/demo/episodes/2/script")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["script_file"] == "episode_2.json"

    def test_preprocess_narration_runs_skill_script(self, tmp_path, monkeypatch):
        # narration 模式應嘗試呼叫 split_narration_segments.py；
        # 此處 tmp 專案缺少 source 檔案，腳本會以非零碼結束 → endpoint 回 500 並帶腳本名
        pm = _FakePMProj(tmp_path, content_mode="narration")
        client = _client_proj(monkeypatch, pm)
        with client:
            resp = client.post("/api/v1/projects/demo/episodes/1/preprocess")
        assert resp.status_code == 500
        assert "split_narration_segments.py" in resp.json()["detail"]

    def test_preprocess_drama_invokes_subprocess(self, tmp_path, monkeypatch):
        pm = _FakePMProj(tmp_path, content_mode="drama")
        # Pre-create the expected output file so endpoint reports it
        target = tmp_path / "demo" / "drafts" / "episode_1"
        target.mkdir(parents=True, exist_ok=True)
        (target / "step1_normalized_script.md").write_text("# step1", encoding="utf-8")

        called: dict[str, Any] = {}

        def fake_run(args, **kwargs):
            called["args"] = args
            return _FakeProc(returncode=0, stdout="ok")

        import subprocess

        monkeypatch.setattr(subprocess, "run", fake_run)
        client = _client_proj(monkeypatch, pm)

        with client:
            resp = client.post("/api/v1/projects/demo/episodes/1/preprocess")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["content_mode"] == "drama"
        assert "step1_normalized_script.md" in body["step1_path"]
        assert "--episode" in called["args"]


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/v1/projects/missing/generate/storyboards/batch",
        "/api/v1/projects/missing/generate/characters/batch",
    ],
)
def test_batch_404_when_project_missing(tmp_path, monkeypatch, endpoint):
    class _PM:
        def load_project(self, name):
            raise FileNotFoundError(name)

        def load_script(self, name, sf):
            raise FileNotFoundError(sf)

        def get_project_path(self, name):
            raise FileNotFoundError(name)

    queue = _FakeQueue()
    client = _client_gen(monkeypatch, _PM(), queue)
    with client:
        resp = client.post(endpoint, json={"script_file": "episode_1.json"})
    assert resp.status_code == 404
