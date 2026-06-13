from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib.project_manager import ProjectManager

logger = logging.getLogger(__name__)


class LorebookManager:
    """專案世界觀管理（角色、線索道具、場景定義）"""

    def __init__(self, project_manager: ProjectManager):
        self.pm = project_manager

    @staticmethod
    def _needs_generated_sheet(project_dir: Path, entity: dict, sheet_key: str) -> bool:
        # 已有 sheet（含使用者上傳寫入 v0 後指向的 sheet）即不需 AI 生成
        sheet = entity.get(sheet_key)
        return not sheet or not (project_dir / sheet).exists()

    def add_project_character(
        self,
        project_name: str,
        name: str,
        description: str,
        voice_style: str | None = None,
        character_sheet: str | None = None,
    ) -> dict:
        """向專案新增角色（專案級）"""
        project = self.pm.load_project(project_name)

        project.setdefault("characters", {})[name] = {
            "description": description,
            "voice_style": voice_style or "",
            "character_sheet": character_sheet or "",
        }

        self.pm.save_project(project_name, project)
        return project

    def update_project_character_sheet(self, project_name: str, name: str, sheet_path: str) -> dict:
        """更新專案級角色設計圖路徑"""
        project = self.pm.load_project(project_name)

        if name not in project["characters"]:
            raise KeyError(f"角色 '{name}' 不存在")

        project["characters"][name]["character_sheet"] = sheet_path
        self.pm.save_project(project_name, project)
        return project

    def update_character_reference_image(self, project_name: str, char_name: str, ref_path: str) -> dict:
        """更新角色的參考圖路徑"""
        project = self.pm.load_project(project_name)

        if "characters" not in project or char_name not in project["characters"]:
            raise KeyError(f"角色 '{char_name}' 不存在")

        project["characters"][char_name]["reference_image"] = ref_path
        self.pm.save_project(project_name, project)
        return project

    def get_project_character(self, project_name: str, name: str) -> dict:
        """獲取專案級角色定義"""
        project = self.pm.load_project(project_name)

        if name not in project["characters"]:
            raise KeyError(f"角色 '{name}' 不存在")

        return project["characters"][name]

    def update_clue_sheet(self, project_name: str, name: str, sheet_path: str) -> dict:
        """更新線索設計圖路徑"""
        project = self.pm.load_project(project_name)

        if name not in project["clues"]:
            raise KeyError(f"線索 '{name}' 不存在")

        project["clues"][name]["clue_sheet"] = sheet_path
        self.pm.save_project(project_name, project)
        return project

    def get_clue(self, project_name: str, name: str) -> dict:
        """獲取線索定義"""
        project = self.pm.load_project(project_name)

        if name not in project["clues"]:
            raise KeyError(f"線索 '{name}' 不存在")

        return project["clues"][name]

    def get_pending_characters(self, project_name: str) -> list[dict]:
        """獲取待生成設計圖的角色列表"""
        project = self.pm.load_project(project_name)
        project_dir = self.pm.get_project_path(project_name)

        pending = []
        for name, char in project.get("characters", {}).items():
            if self._needs_generated_sheet(project_dir, char, "character_sheet"):
                pending.append({"name": name, **char})

        return pending

    def get_pending_clues(self, project_name: str) -> list[dict]:
        """獲取待生成設計圖的線索列表"""
        project = self.pm.load_project(project_name)
        project_dir = self.pm.get_project_path(project_name)

        pending = []
        for name, clue in project["clues"].items():
            if clue.get("importance") == "major" and self._needs_generated_sheet(project_dir, clue, "clue_sheet"):
                pending.append({"name": name, **clue})

        return pending

    def get_clue_path(self, project_name: str, filename: str) -> Path:
        """獲取線索設計圖路徑"""
        return self.pm.get_project_path(project_name) / "clues" / filename

    def add_character(self, project_name: str, name: str, description: str, voice_style: str = "") -> bool:
        """直接新增角色到 project.json，如果角色已存在，跳過不覆蓋。"""
        project = self.pm.load_project(project_name)

        if name in project.get("characters", {}):
            logger.debug("角色 '%s' 已存在於 project.json，跳過", name)
            return False

        if "characters" not in project:
            project["characters"] = {}

        project["characters"][name] = {
            "description": description,
            "character_sheet": "",
            "voice_style": voice_style,
        }

        self.pm.save_project(project_name, project)
        logger.info("新增角色: %s", name)
        return True

    def add_clue(
        self,
        project_name: str,
        name: str,
        description: str,
        importance: str = "minor",
    ) -> bool:
        """直接新增線索（道具）到 project.json，如果線索已存在，跳過不覆蓋。"""
        project = self.pm.load_project(project_name)

        if name in project.get("clues", {}):
            logger.debug("線索 '%s' 已存在於 project.json，跳過", name)
            return False

        if "clues" not in project:
            project["clues"] = {}

        project["clues"][name] = {
            "description": description,
            "importance": importance,
            "clue_sheet": "",
        }

        self.pm.save_project(project_name, project)
        logger.info("新增線索: %s", name)
        return True

    def add_characters_batch(self, project_name: str, characters: dict[str, dict]) -> int:
        """批次新增角色到 project.json"""
        project = self.pm.load_project(project_name)

        if "characters" not in project:
            project["characters"] = {}

        added = 0
        for name, data in characters.items():
            if name not in project["characters"]:
                project["characters"][name] = {
                    "description": data.get("description", ""),
                    "character_sheet": data.get("character_sheet", ""),
                    "voice_style": data.get("voice_style", ""),
                }
                added += 1
                logger.info("新增角色: %s", name)
            else:
                logger.debug("角色 '%s' 已存在，跳過", name)

        if added > 0:
            self.pm.save_project(project_name, project)

        return added

    def add_clues_batch(self, project_name: str, clues: dict[str, dict]) -> int:
        """批次新增線索到 project.json"""
        project = self.pm.load_project(project_name)

        if "clues" not in project:
            project["clues"] = {}

        added = 0
        for name, data in clues.items():
            if name not in project["clues"]:
                project["clues"][name] = {
                    "description": data.get("description", ""),
                    "importance": data.get("importance", "minor"),
                    "clue_sheet": data.get("clue_sheet", ""),
                }
                added += 1
                logger.info("新增線索: %s", name)
            else:
                logger.debug("線索 '%s' 已存在，跳過", name)

        if added > 0:
            self.pm.save_project(project_name, project)

        return added

    def collect_reference_images(self, project_name: str, scene: dict) -> list[Path]:
        """收集場景所需的所有參考圖"""
        project = self.pm.load_project(project_name)
        project_dir = self.pm.get_project_path(project_name)
        refs = []

        def append_existing(relative_path: str | None) -> None:
            if not relative_path:
                return
            path = project_dir / relative_path
            if path.exists():
                refs.append(path)

        # 角色參考圖
        for char in scene.get("characters_in_scene", []):
            char_data = project["characters"].get(char, {})
            append_existing(char_data.get("character_sheet"))

        # 線索參考圖
        for clue in scene.get("clues_in_scene", []):
            clue_data = project["clues"].get(clue, {})
            append_existing(clue_data.get("clue_sheet"))

        # 場景參考圖（單數欄位，narration 用 scene_in_segment / drama 用 scene_in_scene）
        scene_name = scene.get("scene_in_scene") or scene.get("scene_in_segment")
        if scene_name:
            scene_data = project.get("scenes", {}).get(scene_name, {})
            append_existing(scene_data.get("scene_sheet") or scene_data.get("scene_ref"))

        return refs

    def add_project_scene(
        self,
        project_name: str,
        name: str,
        description: str,
        scene_sheet: str | None = None,
    ) -> dict:
        """向專案新增場景（專案級）"""
        project = self.pm.load_project(project_name)

        # 這裡會用到私有屬性 _scene_entry，我們可以在類別內自行定義或委託 pm
        project.setdefault("scenes", {})[name] = {
            "description": description,
            "scene_sheet": scene_sheet or "",
            "scene_ref": "",
        }

        self.pm.save_project(project_name, project)
        return project

    def update_scene_sheet(self, project_name: str, name: str, sheet_path: str) -> dict:
        """更新場景設計圖路徑"""
        project = self.pm.load_project(project_name)

        if name not in project.get("scenes", {}):
            raise KeyError(f"場景 '{name}' 不存在")

        project["scenes"][name]["scene_sheet"] = sheet_path
        self.pm.save_project(project_name, project)
        return project

    def update_scene_reference_image(self, project_name: str, name: str, ref_path: str) -> dict:
        """更新場景參考圖路徑"""
        project = self.pm.load_project(project_name)

        if name not in project.get("scenes", {}):
            raise KeyError(f"場景 '{name}' 不存在")

        project["scenes"][name]["scene_ref"] = ref_path
        self.pm.save_project(project_name, project)
        return project

    def get_project_scene(self, project_name: str, name: str) -> dict:
        """獲取專案級場景定義"""
        project = self.pm.load_project(project_name)

        if name not in project.get("scenes", {}):
            raise KeyError(f"場景 '{name}' 不存在")

        return project["scenes"][name]

    def get_scene_path(self, project_name: str, filename: str) -> Path:
        """獲取場景設計圖路徑"""
        return self.pm.get_project_path(project_name) / "scenes" / filename

    def get_pending_scene_sheets(self, project_name: str) -> list[dict]:
        """獲取待生成設計圖的場景列表"""
        project = self.pm.load_project(project_name)
        project_dir = self.pm.get_project_path(project_name)

        pending = []
        for name, scene in project.get("scenes", {}).items():
            if self._needs_generated_sheet(project_dir, scene, "scene_sheet"):
                pending.append({"name": name, **scene})

        return pending

    def add_scenes_batch(self, project_name: str, scenes: dict[str, dict]) -> int:
        """批次新增場景到 project.json"""
        project = self.pm.load_project(project_name)

        project_scenes = project.setdefault("scenes", {})

        added = 0
        for name, data in scenes.items():
            if name not in project_scenes:
                project_scenes[name] = {
                    "description": data.get("description", ""),
                    "scene_sheet": data.get("scene_sheet", ""),
                    "scene_ref": "",
                }
                added += 1
                logger.info("新增場景: %s", name)
            else:
                logger.debug("場景 '%s' 已存在，跳過", name)

        if added > 0:
            self.pm.save_project(project_name, project)

        return added

    def update_clue_reference_image(self, project_name: str, name: str, ref_path: str) -> dict:
        """更新線索的參考圖路徑"""
        project = self.pm.load_project(project_name)

        if name not in project.get("clues", {}):
            raise KeyError(f"線索 '{name}' 不存在")

        project["clues"][name]["reference_image"] = ref_path
        self.pm.save_project(project_name, project)
        return project
