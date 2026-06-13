"""Scene-level image_backend / video_backend 覆蓋的整合測試。"""

from __future__ import annotations

import pytest

from lib.project_manager import ProjectManager


@pytest.fixture()
def pm_env(tmp_path):
    pm = ProjectManager(str(tmp_path))
    project_name = "demo"
    pm.create_project(project_name)
    pm.create_project_metadata(project_name, "Demo", "Anime", "narration")
    return pm, project_name


def _write_narration_script(pm: ProjectManager, project_name: str) -> str:
    script = {
        "title": "Episode 1",
        "content_mode": "narration",
        "segments": [
            {"segment_id": "E1S01", "duration_seconds": 6},
            {"segment_id": "E1S02", "duration_seconds": 8},
        ],
    }
    filename = "episode_1.json"
    pm.save_script(project_name, script, filename)
    return filename


def _write_drama_script(pm: ProjectManager, project_name: str) -> str:
    script = {
        "title": "Episode 1",
        "scenes": [
            {"scene_id": "scene_1", "duration_seconds": 8},
        ],
    }
    filename = "episode_1.json"
    pm.save_script(project_name, script, filename)
    return filename


@pytest.fixture()
def patched_generate_router(pm_env, monkeypatch):
    pm, project_name = pm_env
    from server.routers import generate as generate_router

    monkeypatch.setattr(generate_router, "get_project_manager", lambda: pm)
    return generate_router, pm, project_name


class TestUpdateSceneBackend:
    def test_set_image_backend_only(self, pm_env):
        pm, project_name = pm_env
        filename = _write_narration_script(pm, project_name)

        pm.update_scene_backend(
            project_name=project_name,
            script_filename=filename,
            scene_id="E1S01",
            image_backend="openai/gpt-image-1",
        )

        saved = pm.load_script(project_name, filename)
        seg = saved["segments"][0]
        assert seg["image_backend"] == "openai/gpt-image-1"
        assert "video_backend" not in seg
        # 其他 segment 不受影響
        assert "image_backend" not in saved["segments"][1]

    def test_set_both_backends(self, pm_env):
        pm, project_name = pm_env
        filename = _write_drama_script(pm, project_name)

        pm.update_scene_backend(
            project_name=project_name,
            script_filename=filename,
            scene_id="scene_1",
            image_backend="openai/gpt-image-2",
            video_backend="ark/doubao-seedance-pro",
        )

        saved = pm.load_script(project_name, filename)
        scene = saved["scenes"][0]
        assert scene["image_backend"] == "openai/gpt-image-2"
        assert scene["video_backend"] == "ark/doubao-seedance-pro"

    def test_clear_backend_with_none(self, pm_env):
        pm, project_name = pm_env
        filename = _write_narration_script(pm, project_name)

        # 先設定
        pm.update_scene_backend(
            project_name=project_name,
            script_filename=filename,
            scene_id="E1S01",
            image_backend="openai/gpt-image-1",
        )
        # 再清除
        pm.update_scene_backend(
            project_name=project_name,
            script_filename=filename,
            scene_id="E1S01",
            image_backend=None,
        )

        saved = pm.load_script(project_name, filename)
        seg = saved["segments"][0]
        assert "image_backend" not in seg

    def test_partial_update_does_not_touch_other_field(self, pm_env):
        pm, project_name = pm_env
        filename = _write_drama_script(pm, project_name)

        # 先設兩個欄位
        pm.update_scene_backend(
            project_name=project_name,
            script_filename=filename,
            scene_id="scene_1",
            image_backend="openai/gpt-image-1",
            video_backend="ark/doubao-seedance-pro",
        )
        # 只改 video，image 應保留
        pm.update_scene_backend(
            project_name=project_name,
            script_filename=filename,
            scene_id="scene_1",
            video_backend="gemini-aistudio/veo-3.1-lite-generate-preview",
        )

        saved = pm.load_script(project_name, filename)
        scene = saved["scenes"][0]
        assert scene["image_backend"] == "openai/gpt-image-1"
        assert scene["video_backend"] == "gemini-aistudio/veo-3.1-lite-generate-preview"

    def test_unknown_scene_raises(self, pm_env):
        pm, project_name = pm_env
        filename = _write_narration_script(pm, project_name)

        with pytest.raises(KeyError):
            pm.update_scene_backend(
                project_name=project_name,
                script_filename=filename,
                scene_id="不存在",
                image_backend="openai/gpt-image-1",
            )


class TestSnapshotReadsSceneOverride:
    """驗證 enqueue 端的 snapshot helper 讀到 scene 覆蓋。"""

    def test_snapshot_image_backend_uses_scene_override(self, patched_generate_router):
        generate_router, pm, project_name = patched_generate_router
        filename = _write_narration_script(pm, project_name)
        pm.update_scene_backend(
            project_name=project_name,
            script_filename=filename,
            scene_id="E1S01",
            image_backend="openai/gpt-image-1",
        )

        result = generate_router._snapshot_image_backend(
            project_name,
            script_file=filename,
            resource_id="E1S01",
        )

        assert result == {"image_provider": "openai", "image_model": "gpt-image-1"}

    def test_snapshot_image_backend_falls_back_to_project(self, patched_generate_router):
        generate_router, pm, project_name = patched_generate_router
        # 先建 project.json
        pm.create_project_metadata(project_name, "Demo", "Anime", "narration")
        filename = _write_narration_script(pm, project_name)
        # 設專案級
        project = pm.load_project(project_name)
        project["image_backend"] = "openai/gpt-image-2"
        pm.save_project(project_name, project)

        # scene 沒有覆蓋 → 走專案層級
        result = generate_router._snapshot_image_backend(
            project_name,
            script_file=filename,
            resource_id="E1S01",
        )

        assert result == {"image_provider": "openai", "image_model": "gpt-image-2"}

    def test_snapshot_video_backend_uses_scene_override(self, patched_generate_router):
        generate_router, pm, project_name = patched_generate_router
        filename = _write_drama_script(pm, project_name)
        pm.update_scene_backend(
            project_name=project_name,
            script_filename=filename,
            scene_id="scene_1",
            video_backend="ark/doubao-seedance-pro",
        )

        result = generate_router._snapshot_video_backend(
            project_name,
            script_file=filename,
            resource_id="scene_1",
        )

        assert result["video_provider"] == "ark"
        assert result["video_provider_settings"] == {"model": "doubao-seedance-pro"}

    def test_snapshot_video_backend_empty_when_no_scene_override(self, patched_generate_router):
        generate_router, pm, project_name = patched_generate_router
        filename = _write_drama_script(pm, project_name)

        result = generate_router._snapshot_video_backend(
            project_name,
            script_file=filename,
            resource_id="scene_1",
        )

        # 無 scene 覆蓋 → 不快照（保持原 fallback 至 _resolve_video_backend）
        assert result == {}
