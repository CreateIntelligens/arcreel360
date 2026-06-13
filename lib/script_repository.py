"""
劇本與場景領域資料存取。

封裝 scripts/*.json 的讀寫、正規化、場景狀態與分鏡欄位更新。
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lib.entity_reconciler import reconcile_script
from lib.project_change_hints import emit_project_change_hint
from lib.project_paths import ProjectPaths
from lib.project_store import ProjectStore
from lib.storyboard_sequence import find_storyboard_item, get_storyboard_items

logger = logging.getLogger(__name__)

EPISODE_FILENAME_PATTERN = re.compile(r"episode[_\s]*(\d+)", re.IGNORECASE)


class _BackendUnset:
    """Sentinel for backend fields omitted from a partial update."""


_BACKEND_UNSET = _BackendUnset()


def _apply_scene_backend(item: dict, field: str, value: str | None | _BackendUnset) -> None:
    if value is _BACKEND_UNSET:
        return
    if value is None:
        item.pop(field, None)
        return
    item[field] = value


def _episode_from_filename(filename: str) -> int | None:
    """從劇本檔名解析集數，如 episode_2.json → 2；無法解析時回傳 None。"""
    match = EPISODE_FILENAME_PATTERN.search(filename)
    return int(match.group(1)) if match else None


def _next_display_order(episodes: list[dict]) -> int:
    """回傳下一個顯示順序值（max(現有 order) + 1，無資料時為 0）。"""
    max_order = -1
    for ep in episodes:
        value = ep.get("order")
        if isinstance(value, int) and value > max_order:
            max_order = value
    return max_order + 1


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ScriptRepository:
    """劇本與場景的領域邏輯：CRUD、正規化、場景狀態。"""

    def __init__(
        self,
        *,
        paths: ProjectPaths,
        store: ProjectStore,
        sync_characters: Callable[[str, str], Any] | None = None,
        sync_clues: Callable[[str, str], Any] | None = None,
    ):
        self._paths = paths
        self._store = store
        self._sync_characters = sync_characters or (lambda *_args: None)
        self._sync_clues = sync_clues or (lambda *_args: None)

    @staticmethod
    def _scene_entry(description: str, scene_sheet: str = "") -> dict:
        return {
            "description": description,
            "scene_sheet": scene_sheet,
            "scene_ref": "",
        }

    @staticmethod
    def _needs_generated_sheet(project_dir: Path, entity: dict, sheet_key: str) -> bool:
        sheet = entity.get(sheet_key)
        return not sheet or not (project_dir / sheet).exists()

    def create_script(self, project_name: str, title: str, chapter: str) -> dict:
        """
        建立新的分鏡劇本模板。

        保持 ProjectManager 既有行為：只回傳 dict，不主動寫檔。
        """
        return {
            "novel": {"title": title, "chapter": chapter},
            "scenes": [],
            "metadata": {
                "created_at": _utc_now_iso(),
                "updated_at": _utc_now_iso(),
                "total_scenes": 0,
                "estimated_duration_seconds": 0,
                "status": "draft",
            },
        }

    def save_script(self, project_name: str, script: dict, filename: str | None = None) -> Path:
        """儲存分鏡劇本。"""
        project_dir = self._paths.get_project_path(project_name)
        scripts_dir = project_dir / "scripts"

        if filename is not None and filename.startswith("scripts/"):
            filename = filename[len("scripts/") :]

        if filename is None:
            chapter = script["novel"].get("chapter", "chapter_01")
            filename = f"{chapter.replace(' ', '_')}_script.json"

        filename_episode = _episode_from_filename(filename)
        if filename_episode is not None and script.get("episode") != filename_episode:
            logger.warning(
                "劇本內容 episode=%s 與檔名集數=%s 不一致，以檔名為準校正 project=%s file=%s",
                script.get("episode"),
                filename_episode,
                project_name,
                filename,
            )
            script["episode"] = filename_episode
            for items_key in ("segments", "scenes"):
                items = script.get(items_key)
                if not isinstance(items, list):
                    continue
                for item in items:
                    if isinstance(item, dict) and "episode" in item:
                        item["episode"] = filename_episode

        now = _utc_now_iso()

        try:
            project_json = self._store.load_project(project_name)
            script = reconcile_script(script, project_json)
        except Exception:
            logger.warning("關聯補齊失敗，沿用原劇本繼續存檔: %s", project_name, exc_info=True)

        metadata = script.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            script["metadata"] = metadata
        metadata.setdefault("created_at", now)
        metadata.setdefault("status", "draft")
        metadata["updated_at"] = now

        scenes = script.get("scenes", [])
        if not isinstance(scenes, list):
            scenes = []
        segments = script.get("segments", [])
        if not isinstance(segments, list):
            segments = []

        content_mode = script.get("content_mode", "narration")
        if content_mode == "narration" and segments:
            items = segments
            items_type = "segments"
        elif scenes:
            items = scenes
            items_type = "scenes"
        else:
            items = segments
            items_type = "segments"

        metadata["total_scenes"] = len(items)
        default_duration = 4 if items_type == "segments" else 8
        metadata["estimated_duration_seconds"] = sum(item.get("duration_seconds", default_duration) for item in items)

        real = self._paths._safe_subpath(scripts_dir, filename)
        output_path = Path(real)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        ProjectStore._atomic_write_json(output_path, script)

        emit_project_change_hint(
            project_name,
            changed_paths=[f"scripts/{output_path.name}"],
        )

        if self._store.project_exists(project_name) and isinstance(script.get("episode"), int):
            self.sync_episode_from_script(project_name, filename)

        return output_path

    def sync_episode_from_script(self, project_name: str, script_filename: str) -> dict:
        """從劇本檔案同步集數資訊到 project.json。"""
        script = self.load_script(project_name, script_filename)
        project = self._store.load_project(project_name)

        episode_num = script.get("episode", 1)
        episode_title = (script.get("title") or "").strip()
        if not episode_title:
            return project

        script_file = f"scripts/{script_filename}"

        episodes = project.setdefault("episodes", [])
        episode_entry = next((ep for ep in episodes if ep["episode"] == episode_num), None)

        if episode_entry is None:
            episode_entry = {"episode": episode_num, "order": _next_display_order(episodes)}
            episodes.append(episode_entry)
        elif episode_entry.get("title") == episode_title and episode_entry.get("script_file") == script_file:
            return project

        episode_entry["title"] = episode_title
        episode_entry["script_file"] = script_file
        episodes.sort(key=lambda x: x["episode"])
        self._store.save_project(project_name, project)

        logger.info("已同步劇集資訊: Episode %d - %s", episode_num, episode_title)
        return project

    def load_script(self, project_name: str, filename: str) -> dict:
        """載入分鏡劇本。"""
        project_dir = self._paths.get_project_path(project_name)
        if filename.startswith("scripts/"):
            filename = filename[len("scripts/") :]
        real = self._paths._safe_subpath(project_dir / "scripts", filename)

        if not os.path.exists(real):
            raise FileNotFoundError(f"劇本檔案不存在: {real}")

        with open(real, encoding="utf-8") as f:  # noqa: PTH123
            return json.load(f)

    def list_scripts(self, project_name: str) -> list[str]:
        """列出專案中的所有劇本。"""
        project_dir = self._paths.get_project_path(project_name)
        scripts_dir = project_dir / "scripts"
        return [f.name for f in scripts_dir.glob("*.json")]

    def update_character_sheet(self, project_name: str, script_filename: str, name: str, sheet_path: str) -> dict:
        """更新劇本內舊格式角色設計圖路徑。"""
        script = self.load_script(project_name, script_filename)

        if name not in script["characters"]:
            raise KeyError(f"角色 '{name}' 不存在")

        script["characters"][name]["character_sheet"] = sheet_path
        self.save_script(project_name, script, script_filename)
        return script

    @staticmethod
    def create_generated_assets(content_mode: str = "narration") -> dict:
        """建立標準的 generated_assets 結構。"""
        return {
            "storyboard_image": None,
            "video_clip": None,
            "video_thumbnail": None,
            "video_uri": None,
            "status": "pending",
        }

    @staticmethod
    def create_scene_template(scene_id: str, episode: int = 1, duration_seconds: int = 8) -> dict:
        """建立標準場景物件模板。"""
        return {
            "scene_id": scene_id,
            "episode": episode,
            "title": "",
            "scene_type": "劇情",
            "duration_seconds": duration_seconds,
            "segment_break": False,
            "characters_in_scene": [],
            "clues_in_scene": [],
            "visual": {
                "description": "",
                "shot_type": "medium shot",
                "camera_movement": "static",
                "lighting": "",
                "mood": "",
            },
            "action": "",
            "dialogue": {"speaker": "", "text": "", "emotion": "neutral"},
            "audio": {"dialogue": [], "narration": "", "sound_effects": []},
            "transition_to_next": "cut",
            "generated_assets": ScriptRepository.create_generated_assets(),
        }

    def normalize_scene(self, scene: dict, episode: int = 1) -> dict:
        """補全單個場景中缺失的欄位。"""
        template = self.create_scene_template(
            scene_id=scene.get("scene_id", "000"),
            episode=episode,
            duration_seconds=scene.get("duration_seconds", 8),
        )

        if "visual" not in scene:
            scene["visual"] = template["visual"]
        else:
            for key in template["visual"]:
                if key not in scene["visual"]:
                    scene["visual"][key] = template["visual"][key]

        if "audio" not in scene:
            scene["audio"] = template["audio"]
        else:
            for key in template["audio"]:
                if key not in scene["audio"]:
                    scene["audio"][key] = template["audio"][key]

        if "generated_assets" not in scene:
            scene["generated_assets"] = self.create_generated_assets()
        else:
            assets_template = self.create_generated_assets()
            for key in assets_template:
                if key not in scene["generated_assets"]:
                    scene["generated_assets"][key] = assets_template[key]

        top_level_defaults = {
            "episode": episode,
            "title": "",
            "scene_type": "劇情",
            "segment_break": False,
            "characters_in_scene": [],
            "clues_in_scene": [],
            "action": "",
            "dialogue": template["dialogue"],
            "transition_to_next": "cut",
        }

        for key, default_value in top_level_defaults.items():
            if key not in scene:
                scene[key] = default_value

        self.update_scene_status(scene)
        return scene

    def update_scene_status(self, scene: dict) -> str:
        """根據 generated_assets 內容更新並返回場景狀態。"""
        assets = scene.get("generated_assets", {})

        has_image = bool(assets.get("storyboard_image"))
        has_video = bool(assets.get("video_clip"))

        if has_video:
            status = "completed"
        elif has_image:
            status = "storyboard_ready"
        else:
            status = "pending"

        assets["status"] = status
        return status

    def normalize_script(self, project_name: str, script_filename: str, save: bool = True) -> dict:
        """補全現有 script.json 中缺失的欄位。"""
        script = self.load_script(project_name, script_filename)

        episode = script.get("episode", 1)
        if not episode:
            match = re.search(r"episode[_\s]*(\d+)", script_filename, re.IGNORECASE)
            episode = int(match.group(1)) if match else 1

        script_defaults = {
            "episode": episode,
            "title": script.get("novel", {}).get("chapter", ""),
            "duration_seconds": 0,
            "summary": "",
        }

        for key, default_value in script_defaults.items():
            if key not in script:
                script[key] = default_value

        if "novel" not in script:
            script["novel"] = {"title": "", "chapter": ""}
        if isinstance(script.get("novel"), dict):
            script["novel"].pop("source_file", None)

        if "characters" in script and isinstance(script["characters"], dict) and script["characters"]:
            logger.warning("檢測到舊格式 characters 物件，自動同步到 project.json")
            self._sync_characters(project_name, script_filename)
            script = self.load_script(project_name, script_filename)

        if "clues" in script and isinstance(script["clues"], dict) and script["clues"]:
            logger.warning("檢測到舊格式 clues 物件，自動同步到 project.json")
            self._sync_clues(project_name, script_filename)
            script = self.load_script(project_name, script_filename)

        if "scenes" not in script:
            script["scenes"] = []

        if "metadata" not in script:
            script["metadata"] = {
                "created_at": _utc_now_iso(),
                "updated_at": _utc_now_iso(),
                "total_scenes": 0,
                "estimated_duration_seconds": 0,
                "status": "draft",
            }

        for scene in script["scenes"]:
            self.normalize_scene(scene, episode)

        script["metadata"]["total_scenes"] = len(script["scenes"])
        script["metadata"]["estimated_duration_seconds"] = sum(s.get("duration_seconds", 8) for s in script["scenes"])
        script["duration_seconds"] = script["metadata"]["estimated_duration_seconds"]

        if save:
            self.save_script(project_name, script, script_filename)
            logger.info("劇本已規範化並儲存: %s", script_filename)

        return script

    def add_scene(self, project_name: str, script_filename: str, scene: dict) -> dict:
        """向劇本新增場景。"""
        script = self.load_script(project_name, script_filename)

        existing_ids = [s["scene_id"] for s in script["scenes"]]
        next_id = f"{len(existing_ids) + 1:03d}"
        scene["scene_id"] = next_id

        if "generated_assets" not in scene:
            scene["generated_assets"] = {
                "storyboard_image": None,
                "video_clip": None,
                "status": "pending",
            }

        script["scenes"].append(scene)
        self.save_script(project_name, script, script_filename)
        return script

    def update_scene_asset(
        self,
        project_name: str,
        script_filename: str,
        scene_id: str,
        asset_type: str,
        asset_path: str,
    ) -> dict:
        """更新場景的生成資源路徑。"""
        script = self.load_script(project_name, script_filename)
        content_mode = script.get("content_mode", "narration")
        items, id_field, _, _, _ = get_storyboard_items(script)

        for item in items:
            if str(item.get(id_field)) == str(scene_id):
                assets = item.get("generated_assets")
                if not isinstance(assets, dict):
                    assets = {}
                    item["generated_assets"] = assets

                assets_template = self.create_generated_assets(content_mode)
                for key, default_value in assets_template.items():
                    if key not in assets:
                        assets[key] = default_value

                assets[asset_type] = asset_path
                self.update_scene_status(item)
                self.save_script(project_name, script, script_filename)
                return script

        raise KeyError(f"場景 '{scene_id}' 不存在")

    def update_scene_backend(
        self,
        project_name: str,
        script_filename: str,
        scene_id: str,
        *,
        image_backend: str | None | _BackendUnset = _BACKEND_UNSET,
        video_backend: str | None | _BackendUnset = _BACKEND_UNSET,
    ) -> dict:
        """更新 scene 的 image_backend / video_backend 覆蓋設定。"""
        script = self.load_script(project_name, script_filename)
        items, id_field, _, _, _ = get_storyboard_items(script)
        resolved = find_storyboard_item(items, id_field, scene_id)
        if resolved is None:
            raise KeyError(f"場景 '{scene_id}' 不存在")

        item, _ = resolved
        _apply_scene_backend(item, "image_backend", image_backend)
        _apply_scene_backend(item, "video_backend", video_backend)
        self.save_script(project_name, script, script_filename)
        return item

    def get_pending_scenes(self, project_name: str, script_filename: str, asset_type: str) -> list[dict]:
        """獲取待處理的場景/片段列表。"""
        script = self.load_script(project_name, script_filename)
        items, _, _, _, _ = get_storyboard_items(script)

        return [item for item in items if not item["generated_assets"].get(asset_type)]

    def get_scenes_needing_storyboard(self, project_name: str, script_filename: str) -> list[dict]:
        """獲取需要生成分鏡圖的場景/片段列表。"""
        script = self.load_script(project_name, script_filename)
        items, _, _, _, _ = get_storyboard_items(script)

        return [item for item in items if not item.get("generated_assets", {}).get("storyboard_image")]

    def _find_script_filename_by_scene_id(self, project_name: str, scene_id: str) -> str:
        """遍歷專案 episodes 中的劇本，查找包含特定 scene_id 或 segment_id 的劇本檔名。"""
        project = self._store.load_project(project_name)
        for ep in project.get("episodes", []):
            script_filename = ep.get("script_file")
            if not script_filename:
                continue
            try:
                script_name = (
                    script_filename[len("scripts/") :] if script_filename.startswith("scripts/") else script_filename
                )
                script = self.load_script(project_name, script_name)
                for key in ("segments", "scenes"):
                    for item in script.get(key, []) or []:
                        if str(item.get("segment_id") or item.get("scene_id")) == str(scene_id):
                            return script_name
            except Exception:
                continue
        raise KeyError(f"在專案 '{project_name}' 中找不到包含場景 ID '{scene_id}' 的劇本")

    def update_storyboard_reference_image(self, project_name: str, name: str, ref_path: str) -> dict:
        """更新分鏡參考圖路徑 (reference_image)。"""
        return self._update_storyboard_item_field(project_name, name, "reference_image", ref_path)

    def update_storyboard_sheet(self, project_name: str, name: str, sheet_path: str) -> dict:
        """更新分鏡設計圖/當前參考圖路徑 (storyboard_sheet)。"""
        return self._update_storyboard_item_field(project_name, name, "storyboard_sheet", sheet_path)

    def _update_storyboard_item_field(self, project_name: str, name: str, field: str, value: str) -> dict:
        script_name = self._find_script_filename_by_scene_id(project_name, name)
        script = self.load_script(project_name, script_name)
        items, id_field, _, _, _ = get_storyboard_items(script)
        resolved = find_storyboard_item(items, id_field, name)
        if resolved is not None:
            item, _ = resolved
            item[field] = value
            self.save_script(project_name, script, script_name)
            return script
        raise KeyError(f"場景 '{name}' 不存在於劇本 {script_name} 中")
