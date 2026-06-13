import json
import warnings
from pathlib import Path

import pytest

from lib.project_manager import ProjectManager


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class _FakeTextBackend:
    @property
    def name(self):
        return "fake"

    @property
    def model(self):
        return "fake-model"

    @property
    def capabilities(self):
        return set()

    async def generate(self, request):
        from lib.text_backends.base import TextGenerationResult

        return TextGenerationResult(
            text=json.dumps(
                {
                    "synopsis": "故事梗概",
                    "genre": "懸疑",
                    "theme": "真相",
                    "world_setting": "古代",
                },
                ensure_ascii=False,
            ),
            provider="fake",
            model="fake-model",
        )


class TestProjectManagerMore:
    def test_project_and_status_lifecycle(self, tmp_path):
        pm = ProjectManager(tmp_path / "projects")
        project_dir = pm.create_project("demo")
        pm.create_project_metadata("demo", "Demo", "Anime", "narration")

        _write(project_dir / "source" / "a.txt", "source")
        _write(project_dir / "scripts" / "episode_1.json", "{}")
        _write(project_dir / "characters" / "alice.png", "x")
        _write(project_dir / "clues" / "clue.png", "x")
        _write(project_dir / "storyboards" / "scene_1.png", "x")
        _write(project_dir / "videos" / "scene_1.mp4", "x")
        _write(project_dir / "output" / "final.mp4", "x")

        assert "demo" in pm.list_projects()
        status = pm.get_project_status("demo")
        assert status["current_stage"] == "completed"
        assert status["source_files"] == ["a.txt"]

        assert pm.project_exists("demo")
        loaded = pm.load_project("demo")
        assert loaded["title"] == "Demo"

        loaded["style"] = "Noir"
        pm.save_project("demo", loaded)
        assert pm.load_project("demo")["style"] == "Noir"

    def test_project_identifier_validation_and_title_fallback(self, tmp_path):
        pm = ProjectManager(tmp_path / "projects")

        with pytest.raises(ValueError):
            pm.create_project("bad name")
        with pytest.raises(ValueError):
            pm.create_project("bad_name")

        pm.create_project("demo")
        project = pm.create_project_metadata("demo", "")

        assert project["title"] == "demo"

    def test_generate_project_name_is_unique_and_safe(self, tmp_path):
        pm = ProjectManager(tmp_path / "projects")

        first = pm.generate_project_name("My Demo Project")
        second = pm.generate_project_name("我的專案")

        assert first.startswith("my-demo-project-")
        assert second.startswith("project-")
        assert first != second
        assert pm.normalize_project_name(first) == first
        assert pm.normalize_project_name(second) == second

    def test_script_operations_and_scene_updates(self, tmp_path):
        pm = ProjectManager(tmp_path / "projects")
        pm.create_project("demo")
        pm.create_project_metadata("demo", "Demo", "Anime", "narration")

        script = {
            "episode": 1,
            "title": "第一集",
            "content_mode": "narration",
            "segments": [{"segment_id": "E1S01", "duration_seconds": 4}],
        }
        path = pm.save_script("demo", script, "episode_1.json")
        assert path.name == "episode_1.json"

        loaded = pm.load_script("demo", "episode_1.json")
        assert loaded["metadata"]["total_scenes"] == 1
        assert loaded["metadata"]["estimated_duration_seconds"] == 4
        assert pm.list_scripts("demo") == ["episode_1.json"]

        synced = pm.sync_episode_from_script("demo", "episode_1.json")
        assert synced["episodes"][0]["episode"] == 1

        # add_scene (drama format)
        drama_script = {
            "episode": 2,
            "title": "第二集",
            "content_mode": "drama",
            "scenes": [],
        }
        pm.save_script("demo", drama_script, "episode_2.json")
        pm.add_scene("demo", "episode_2.json", {"duration_seconds": 8, "generated_assets": {}})
        loaded_drama = pm.load_script("demo", "episode_2.json")
        assert loaded_drama["scenes"][0]["scene_id"] == "001"

        # update_scene_asset + pending helpers
        narration_script = pm.load_script("demo", "episode_1.json")
        narration_script["segments"][0]["generated_assets"] = {}
        pm.save_script("demo", narration_script, "episode_1.json")

        pm.update_scene_asset(
            "demo",
            "episode_1.json",
            "E1S01",
            "storyboard_image",
            "storyboards/scene_E1S01.png",
        )
        updated = pm.load_script("demo", "episode_1.json")
        assert updated["segments"][0]["generated_assets"]["status"] == "storyboard_ready"

        pending_video = pm.get_pending_scenes("demo", "episode_1.json", "video_clip")
        assert len(pending_video) == 1

        # get_scenes_needing_storyboard
        drama = pm.load_script("demo", "episode_2.json")
        drama["scenes"][0]["generated_assets"] = {"storyboard_image": None}
        pm.save_script("demo", drama, "episode_2.json")
        assert len(pm.get_scenes_needing_storyboard("demo", "episode_2.json")) == 1

        with pytest.raises(KeyError):
            pm.update_scene_asset("demo", "episode_1.json", "NOT_FOUND", "video_clip", "x.mp4")

    def test_load_script_strips_scripts_prefix(self, tmp_path):
        """load_script / save_script / update_scene_asset 應相容帶 scripts/ 字首的檔名"""
        pm = ProjectManager(tmp_path / "projects")
        pm.create_project("demo")
        pm.create_project_metadata("demo", "Demo", "Anime", "narration")

        script = {
            "episode": 1,
            "title": "第一集",
            "content_mode": "narration",
            "segments": [{"segment_id": "E1S01", "duration_seconds": 4, "generated_assets": {}}],
        }
        pm.save_script("demo", script, "episode_1.json")

        # 純檔名
        loaded1 = pm.load_script("demo", "episode_1.json")
        assert loaded1["episode"] == 1

        # 帶 scripts/ 字首（前端傳入的格式）
        loaded2 = pm.load_script("demo", "scripts/episode_1.json")
        assert loaded2["episode"] == 1

        # save_script 也應相容帶字首的檔名
        script["title"] = "修改後"
        pm.save_script("demo", script, "scripts/episode_1.json")
        loaded3 = pm.load_script("demo", "episode_1.json")
        assert loaded3["title"] == "修改後"

        # update_scene_asset 也應相容
        pm.update_scene_asset(
            "demo", "scripts/episode_1.json", "E1S01", "storyboard_image", "storyboards/scene_E1S01.png"
        )
        updated = pm.load_script("demo", "episode_1.json")
        assert updated["segments"][0]["generated_assets"]["storyboard_image"] == "storyboards/scene_E1S01.png"

    def test_normalize_and_templates(self, tmp_path):
        pm = ProjectManager(tmp_path / "projects")
        pm.create_project("demo")
        pm.create_project_metadata("demo", "Demo", "Anime", "drama")

        scene = {"scene_id": "S1", "generated_assets": {}}
        normalized = pm.normalize_scene(scene, episode=3)
        assert normalized["episode"] == 3
        assert normalized["generated_assets"]["status"] == "pending"

        assert pm.update_scene_status({"generated_assets": {"video_clip": "v.mp4"}}) == "completed"
        assert pm.update_scene_status({"generated_assets": {"storyboard_image": "s.png"}}) == "storyboard_ready"
        assert pm.update_scene_status({"generated_assets": {}}) == "pending"

        raw_script = {
            "novel": {"chapter": "chapter"},
            "scenes": [{"scene_id": "001"}],
            "characters": {"A": {"description": "desc"}},
            "clues": {"C": {"type": "prop", "description": "d", "importance": "major"}},
        }
        _write(tmp_path / "projects" / "demo" / "scripts" / "legacy.json", json.dumps(raw_script, ensure_ascii=False))

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(pm, "sync_characters_from_script", lambda *args, **kwargs: None, raising=False)
        monkeypatch.setattr(pm, "sync_clues_from_script", lambda *args, **kwargs: None, raising=False)
        normalized_script = pm.normalize_script("demo", "legacy.json", save=False)
        monkeypatch.undo()

        assert "metadata" in normalized_script
        assert normalized_script["duration_seconds"] >= 0

    def test_entity_and_batch_management_and_paths(self, tmp_path):
        pm = ProjectManager(tmp_path / "projects")
        pm.create_project("demo")
        pm.create_project_metadata("demo", "Demo")

        pm.add_project_character("demo", "Alice", "hero", "soft")
        pm.update_project_character_sheet("demo", "Alice", "characters/Alice.png")
        pm.update_character_reference_image("demo", "Alice", "characters/refs/Alice.png")
        assert pm.get_project_character("demo", "Alice")["reference_image"].endswith("Alice.png")

        pm.add_clues_batch("demo", {"玉佩": {"type": "prop", "description": "d", "importance": "major"}})
        pm.update_clue_sheet("demo", "玉佩", "clues/玉佩.png")
        assert pm.get_clue("demo", "玉佩")["clue_sheet"].endswith("玉佩.png")

        project_dir = pm.get_project_path("demo")
        (project_dir / "clues" / "玉佩.png").write_bytes(b"png")
        assert pm.get_pending_clues("demo") == []

        # direct add_* return bool
        assert pm.add_character("demo", "Bob", "side", "") is True
        assert pm.add_character("demo", "Bob", "side", "") is False
        assert pm.add_clue("demo", "線索X", "desc", "minor") is True
        assert pm.add_clue("demo", "線索X", "desc", "minor") is False

        added_chars = pm.add_characters_batch("demo", {"Bob": {"description": "d"}, "C": {"description": "d"}})
        assert added_chars == 1
        added_clues = pm.add_clues_batch("demo", {"線索X": {"description": "d"}, "線索Y": {"description": "d"}})
        assert added_clues == 1

        pm.add_episode("demo", 1, "第一集", "scripts/episode_1.json")
        pm.add_episode("demo", 1, "第一集-改", "scripts/episode_1.json")
        assert pm.load_project("demo")["episodes"][0]["title"].startswith("第一集")

        assert str(pm.get_source_path("demo", "a.txt")).endswith("/source/a.txt")
        assert str(pm.get_character_path("demo", "a.png")).endswith("/characters/a.png")
        assert str(pm.get_storyboard_path("demo", "a.png")).endswith("/storyboards/a.png")
        assert str(pm.get_video_path("demo", "a.mp4")).endswith("/videos/a.mp4")
        assert str(pm.get_output_path("demo", "a.mp4")).endswith("/output/a.mp4")
        assert str(pm.get_clue_path("demo", "a.png")).endswith("/clues/a.png")

        with pytest.raises(KeyError):
            pm.get_project_character("demo", "none")
        with pytest.raises(KeyError):
            pm.update_project_character_sheet("demo", "none", "x")
        with pytest.raises(KeyError):
            pm.update_character_reference_image("demo", "none", "x")
        with pytest.raises(KeyError):
            pm.get_clue("demo", "none")
        with pytest.raises(KeyError):
            pm.update_clue_sheet("demo", "none", "x")

    @pytest.mark.asyncio
    async def test_reference_read_source_and_generate_overview(self, tmp_path, monkeypatch):
        pm = ProjectManager(tmp_path / "projects")
        pm.create_project("demo")
        pm.create_project_metadata("demo", "Demo")

        pm.add_character("demo", "Alice", "hero")
        pm.add_clues_batch("demo", {"玉佩": {"type": "prop", "description": "d", "importance": "major"}})

        project_dir = pm.get_project_path("demo")
        (project_dir / "characters" / "Alice.png").write_bytes(b"png")
        (project_dir / "clues" / "玉佩.png").write_bytes(b"png")

        project = pm.load_project("demo")
        project["characters"]["Alice"]["character_sheet"] = "characters/Alice.png"
        project["clues"]["玉佩"]["clue_sheet"] = "clues/玉佩.png"
        pm.save_project("demo", project)

        refs = pm.collect_reference_images(
            "demo",
            {"characters_in_scene": ["Alice"], "clues_in_scene": ["玉佩"]},
        )
        assert len(refs) == 2

        _write(project_dir / "source" / "1.txt", "a" * 10)
        _write(project_dir / "source" / "2.md", "b" * 10)
        _write(project_dir / "source" / "3.bin", "ignored")
        content = pm._read_source_files("demo", max_chars=15)
        assert "1.txt" in content

        async def _fake_create_backend(*args, **kwargs):
            return _FakeTextBackend()

        monkeypatch.setattr("lib.text_generator.create_text_backend_for_task", _fake_create_backend)
        overview = await pm.generate_overview("demo")
        assert overview["genre"] == "懸疑"
        assert "generated_at" in overview

        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            project_data = pm.sync_project_status("demo")
        assert captured
        assert project_data["title"] == "Demo"

        pm_empty = ProjectManager(tmp_path / "projects-empty")
        pm_empty.create_project("demo")
        pm_empty.create_project_metadata("demo", "Demo")
        with pytest.raises(ValueError):
            await pm_empty.generate_overview("demo")

    def test_read_source_files_includes_docx(self, tmp_path):
        from tests.test_docx_utils import create_fake_docx_bytes

        pm = ProjectManager(tmp_path / "projects")
        pm.create_project("demo")
        pm.create_project_metadata("demo", "Demo")

        project_dir = pm.get_project_path("demo")
        docx_bytes = create_fake_docx_bytes(["第一章內容", "第二段文字"])
        (project_dir / "source" / "novel.docx").write_bytes(docx_bytes)

        content = pm._read_source_files("demo")

        assert "novel.docx" in content
        assert "第一章內容\n第二段文字" in content


class TestFromCwd:
    """Tests for ProjectManager.from_cwd() classmethod."""

    def test_from_cwd_infers_project(self, tmp_path, monkeypatch):
        projects_root = tmp_path / "projects"
        project_dir = projects_root / "my-proj"
        project_dir.mkdir(parents=True)
        (project_dir / "project.json").write_text("{}", encoding="utf-8")

        monkeypatch.chdir(project_dir)
        pm, name = ProjectManager.from_cwd()
        assert name == "my-proj"
        assert pm.projects_root == projects_root

    def test_from_cwd_raises_when_no_project_json(self, tmp_path, monkeypatch):
        project_dir = tmp_path / "projects" / "empty"
        project_dir.mkdir(parents=True)

        monkeypatch.chdir(project_dir)
        with pytest.raises(FileNotFoundError, match="不是有效的專案目錄"):
            ProjectManager.from_cwd()


class TestPathTraversalProtection:
    """路徑遍歷防護測試"""

    def test_get_project_path_rejects_traversal(self, tmp_path):
        pm = ProjectManager(tmp_path / "projects")
        pm.create_project("demo")
        # normalize_project_name 的正則先攔截
        with pytest.raises(ValueError):
            pm.get_project_path("../etc")
        with pytest.raises(ValueError):
            pm.get_project_path("demo/../../etc")

    def test_normalize_project_name_rejects_special_chars(self, tmp_path):
        pm = ProjectManager(tmp_path / "projects")
        with pytest.raises(ValueError):
            pm.normalize_project_name("../hack")
        with pytest.raises(ValueError):
            pm.normalize_project_name("foo/bar")
        with pytest.raises(ValueError):
            pm.normalize_project_name("")

    def test_load_script_rejects_traversal_filename(self, tmp_path):
        pm = ProjectManager(tmp_path / "projects")
        pm.create_project("demo")
        pm.create_project_metadata("demo", "Demo")
        with pytest.raises(ValueError, match="非法檔名"):
            pm.load_script("demo", "../../etc/passwd")

    def test_save_script_rejects_traversal_filename(self, tmp_path):
        pm = ProjectManager(tmp_path / "projects")
        pm.create_project("demo")
        pm.create_project_metadata("demo", "Demo")
        script = {"novel": {"chapter": "ch1"}, "scenes": [], "metadata": {}}
        with pytest.raises(ValueError, match="非法檔名"):
            pm.save_script("demo", script, filename="../../evil.json")

    def test_safe_subpath_allows_normal_filenames(self, tmp_path):
        pm = ProjectManager(tmp_path / "projects")
        pm.create_project("demo")
        project_dir = pm.get_project_path("demo")
        scripts_dir = project_dir / "scripts"
        scripts_dir.mkdir(exist_ok=True)
        # 正常檔名不應被攔截
        real = pm._safe_subpath(scripts_dir, "episode_1.json")
        assert real.endswith("episode_1.json")


class TestCommitEpisodeSplit:
    def test_writes_files_and_updates_project(self, tmp_path):
        pm = ProjectManager(tmp_path / "projects")
        pm.create_project("demo")
        pm.create_project_metadata("demo", "Demo")
        proj_dir = pm.get_project_path("demo")
        (proj_dir / "source").mkdir(exist_ok=True)
        (proj_dir / "source" / "novel.txt").write_text("前半。後半。", encoding="utf-8")

        result = pm.commit_episode_split(
            "demo",
            source_rel="source/novel.txt",
            episode=1,
            part_before="前半。",
            part_after="後半。",
            title="第一集",
        )

        assert (proj_dir / "source" / "episode_1.txt").read_text(encoding="utf-8") == "前半。"
        assert (proj_dir / "source" / "_remaining.txt").read_text(encoding="utf-8") == "後半。"
        # 原始檔未被修改
        assert (proj_dir / "source" / "novel.txt").read_text(encoding="utf-8") == "前半。後半。"
        # project.json episodes 多一筆
        assert any(ep["episode"] == 1 and ep.get("title") == "第一集" for ep in result["episodes"])
        # 重新載入確認持久化
        reloaded = pm.load_project("demo")
        assert any(ep["episode"] == 1 for ep in reloaded.get("episodes", []))

    def test_existing_episode_updates_in_place(self, tmp_path):
        pm = ProjectManager(tmp_path / "projects")
        pm.create_project("demo")
        pm.create_project_metadata("demo", "Demo")
        proj_dir = pm.get_project_path("demo")
        (proj_dir / "source").mkdir(exist_ok=True)
        (proj_dir / "source" / "n.txt").write_text("ab", encoding="utf-8")
        pm.commit_episode_split("demo", "source/n.txt", 1, "a", "b", title="舊標題")
        pm.commit_episode_split("demo", "source/n.txt", 1, "a", "b", title="新標題")
        episodes = pm.load_project("demo").get("episodes", [])
        matching = [ep for ep in episodes if ep["episode"] == 1]
        assert len(matching) == 1
        assert matching[0]["title"] == "新標題"

    def test_rejects_source_outside_source_dir(self, tmp_path):
        pm = ProjectManager(tmp_path / "projects")
        pm.create_project("demo")
        pm.create_project_metadata("demo", "Demo")
        with pytest.raises(ValueError, match="source 路徑超出"):
            pm.commit_episode_split("demo", "../../etc/passwd", 1, "a", "b")


class TestEpisodeIndexConsistency:
    """防止「兩個劇本檔撞號」造成事件服務索引同步迴圈的防線。"""

    def _make_pm(self, tmp_path: Path) -> ProjectManager:
        pm = ProjectManager(tmp_path / "projects")
        pm.create_project("demo")
        pm.create_project_metadata("demo", "Demo", "Anime", "narration")
        return pm

    def test_save_script_corrects_episode_to_match_filename(self, tmp_path):
        """內容 episode 與檔名集數不一致時，以檔名為準校正內容。"""
        pm = self._make_pm(tmp_path)
        # 內容宣稱第 1 集，卻存進 episode_2.json
        script = {
            "episode": 1,
            "title": "第二集",
            "content_mode": "narration",
            "segments": [
                {"segment_id": "E1S01", "episode": 1, "duration_seconds": 4},
            ],
        }
        pm.save_script("demo", script, "episode_2.json")

        loaded = pm.load_script("demo", "episode_2.json")
        assert loaded["episode"] == 2
        assert loaded["segments"][0]["episode"] == 2
        # segment_id 不被校正（由生成端決定）
        assert loaded["segments"][0]["segment_id"] == "E1S01"

    def test_save_script_keeps_consistent_episode_untouched(self, tmp_path):
        """內容 episode 與檔名一致時不做任何校正。"""
        pm = self._make_pm(tmp_path)
        script = {
            "episode": 2,
            "title": "第二集",
            "content_mode": "narration",
            "segments": [{"segment_id": "E2S01", "episode": 2, "duration_seconds": 4}],
        }
        pm.save_script("demo", script, "episode_2.json")
        loaded = pm.load_script("demo", "episode_2.json")
        assert loaded["episode"] == 2
        assert loaded["segments"][0]["episode"] == 2

    def test_two_scripts_do_not_collide_after_save(self, tmp_path):
        """即使兩份內容都宣稱 episode=1，存成不同檔名後集數仍互不衝突。"""
        pm = self._make_pm(tmp_path)
        for filename in ("episode_1.json", "episode_2.json"):
            pm.save_script(
                "demo",
                {
                    "episode": 1,
                    "title": filename,
                    "content_mode": "narration",
                    "segments": [],
                },
                filename,
            )
        assert pm.load_script("demo", "episode_1.json")["episode"] == 1
        assert pm.load_script("demo", "episode_2.json")["episode"] == 2

    def test_sync_episode_from_script_is_noop_when_unchanged(self, tmp_path):
        """索引無變化時 sync_episode_from_script 不重寫 project.json。"""
        pm = self._make_pm(tmp_path)
        pm.save_script(
            "demo",
            {"episode": 1, "title": "第一集", "content_mode": "narration", "segments": []},
            "episode_1.json",
        )
        pm.sync_episode_from_script("demo", "episode_1.json")

        project_file = pm.get_project_path("demo") / "project.json"
        before = project_file.stat().st_mtime_ns
        # 第二次同步：內容未變，不應觸發寫入
        pm.sync_episode_from_script("demo", "episode_1.json")
        after = project_file.stat().st_mtime_ns
        assert before == after
