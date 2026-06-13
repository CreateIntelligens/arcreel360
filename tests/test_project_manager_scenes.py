"""場景(scene)實體的 ProjectManager 測試。"""

import pytest

from lib.project_manager import ProjectManager


def _make_pm(tmp_path) -> ProjectManager:
    pm = ProjectManager(tmp_path / "projects")
    pm.create_project("demo")
    pm.create_project_metadata("demo", "Demo", "Anime", "narration")
    return pm


class TestSceneEntity:
    def test_add_and_get_scene(self, tmp_path):
        pm = _make_pm(tmp_path)
        pm.add_project_scene("demo", "古城牆", "斑駁的青磚城牆，黃昏光線")

        scene = pm.get_project_scene("demo", "古城牆")
        assert scene["description"] == "斑駁的青磚城牆，黃昏光線"
        assert scene["scene_sheet"] == ""
        assert scene["scene_ref"] == ""
        assert "use_uploaded_as_final" not in scene

    def test_get_missing_scene_raises(self, tmp_path):
        pm = _make_pm(tmp_path)
        with pytest.raises(KeyError):
            pm.get_project_scene("demo", "不存在")

    def test_update_scene_sheet_and_ref(self, tmp_path):
        pm = _make_pm(tmp_path)
        pm.add_project_scene("demo", "古城牆", "城牆")
        pm.update_scene_sheet("demo", "古城牆", "scenes/古城牆.png")
        pm.update_scene_reference_image("demo", "古城牆", "scenes/refs/古城牆.png")

        scene = pm.get_project_scene("demo", "古城牆")
        assert scene["scene_sheet"] == "scenes/古城牆.png"
        assert scene["scene_ref"] == "scenes/refs/古城牆.png"

    def test_scene_path_and_subdir_created(self, tmp_path):
        pm = _make_pm(tmp_path)
        scenes_dir = pm.get_project_path("demo") / "scenes"
        assert scenes_dir.exists()
        assert pm.get_scene_path("demo", "古城牆.png") == scenes_dir / "古城牆.png"

    def test_add_scenes_batch_skips_existing(self, tmp_path):
        pm = _make_pm(tmp_path)
        pm.add_project_scene("demo", "古城牆", "舊描述")
        added = pm.add_scenes_batch(
            "demo",
            {"古城牆": {"description": "新描述"}, "市集": {"description": "熱鬧市集"}},
        )
        assert added == 1
        assert pm.get_project_scene("demo", "古城牆")["description"] == "舊描述"
        assert pm.get_project_scene("demo", "市集")["description"] == "熱鬧市集"

    def test_pending_scenes_excludes_those_with_sheet(self, tmp_path):
        pm = _make_pm(tmp_path)
        pm.add_project_scene("demo", "待生成", "需要 AI 生成")
        pm.add_project_scene("demo", "已生成", "已有 sheet")

        # 已生成: 寫一個實體檔案 + 指向 sheet（含使用者上傳寫 v0 後的情境）
        sheet_rel = "scenes/已生成.png"
        (pm.get_project_path("demo") / sheet_rel).write_bytes(b"x")
        pm.update_scene_sheet("demo", "已生成", sheet_rel)

        pending = pm.get_pending_scene_sheets("demo")
        names = {p["name"] for p in pending}
        assert names == {"待生成"}

    def test_clue_reference_image_setter(self, tmp_path):
        pm = _make_pm(tmp_path)
        pm.add_clue("demo", "龍紋玉佩", "古玉", "major")
        pm.update_clue_reference_image("demo", "龍紋玉佩", "clues/refs/龍紋玉佩.png")

        clue = pm.get_clue("demo", "龍紋玉佩")
        assert clue["reference_image"] == "clues/refs/龍紋玉佩.png"


class TestLegacyCompat:
    def test_old_project_without_scenes_loads(self, tmp_path):
        """舊 project.json 沒有 scenes 欄位仍可運作。"""
        pm = _make_pm(tmp_path)
        # 模擬舊結構: 只有 characters/clues, 無 scenes key
        project = pm.load_project("demo")
        project["characters"] = {"舊角色": {"description": "x", "character_sheet": ""}}
        project["clues"] = {"舊道具": {"description": "y", "importance": "minor", "clue_sheet": ""}}
        project.pop("scenes", None)
        pm.save_project("demo", project)

        # 不應拋例外
        assert pm.get_pending_characters("demo")[0]["name"] == "舊角色"
        assert pm.get_pending_scene_sheets("demo") == []
        assert pm.load_project("demo").get("scenes", {}) == {}

    def test_collect_reference_images_includes_scene_sheet(self, tmp_path):
        pm = _make_pm(tmp_path)
        pm.add_project_scene("demo", "古城牆", "城牆")
        sheet_rel = "scenes/古城牆.png"
        (pm.get_project_path("demo") / sheet_rel).write_bytes(b"x")
        pm.update_scene_sheet("demo", "古城牆", sheet_rel)

        refs = pm.collect_reference_images("demo", {"scene_in_scene": "古城牆"})
        assert any(r.name == "古城牆.png" for r in refs)

    def test_collect_reference_images_legacy_scene_without_scene_ref(self, tmp_path):
        """沒有 scene_in_scene 的舊 scene dict 不應報錯。"""
        pm = _make_pm(tmp_path)
        pm.add_project_character("demo", "錦衣衛", "黑衣")
        refs = pm.collect_reference_images("demo", {"characters_in_scene": ["錦衣衛"]})
        assert isinstance(refs, list)
