"""
狀態和統計欄位的實時計算器

提供讀時計算的統計欄位，避免儲存冗餘資料。
配合 ProjectManager 使用，在 API 響應時注入計算欄位。
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

OVERVIEW_FIELDS = ("synopsis", "genre", "theme", "world_setting")


class StatusCalculator:
    """狀態和統計欄位的實時計算器"""

    def __init__(self, project_manager):
        """
        初始化狀態計算器

        Args:
            project_manager: ProjectManager 例項
        """
        self.pm = project_manager

    @classmethod
    def _select_content_mode_and_items(cls, script: dict) -> tuple[str, list[dict]]:
        content_mode = script.get("content_mode")
        if content_mode in {"narration", "drama"}:
            if content_mode == "narration" and isinstance(script.get("segments"), list):
                return "narration", script.get("segments", [])
            if content_mode == "drama" and isinstance(script.get("scenes"), list):
                return "drama", script.get("scenes", [])

        if isinstance(script.get("segments"), list):
            return "narration", script.get("segments", [])
        if isinstance(script.get("scenes"), list):
            return "drama", script.get("scenes", [])

        return ("narration" if content_mode not in {"narration", "drama"} else content_mode), []

    def calculate_episode_stats(self, project_name: str, script: dict) -> dict:
        """
        計算單個劇集的統計資訊

        Args:
            project_name: 專案名稱
            script: 劇本資料

        Returns:
            統計資訊字典
        """
        content_mode, items = self._select_content_mode_and_items(script)
        default_duration = 4 if content_mode == "narration" else 8

        # 統計資源完成情況
        storyboard_done = sum(1 for i in items if i.get("generated_assets", {}).get("storyboard_image"))
        video_done = sum(1 for i in items if i.get("generated_assets", {}).get("video_clip"))
        total = len(items)

        # 計算狀態
        if video_done == total and total > 0:
            status = "completed"
        elif storyboard_done > 0 or video_done > 0:
            status = "in_production"
        else:
            status = "draft"

        return {
            "scenes_count": total,
            "status": status,
            "duration_seconds": sum(i.get("duration_seconds", default_duration) for i in items),
            "storyboards": {"total": total, "completed": storyboard_done},
            "videos": {"total": total, "completed": video_done},
        }

    @staticmethod
    def _safe_exists(base: Path, rel_path: str) -> bool:
        """檢查 rel_path 是否為 base 目錄內的合法相對路徑且檔案存在（防止路徑穿越）"""
        if not rel_path:
            return False
        try:
            full = (base / rel_path).resolve()
            return full.is_relative_to(base.resolve()) and full.exists()
        except (OSError, ValueError):
            return False

    def _load_episode_script(
        self, project_name: str, episode_num: int, script_file: str, *, content_mode: str = "narration"
    ) -> tuple:
        """載入單集劇本，返回 (script_status, script|None)，避免重複讀取檔案。
        script_status: 'generated' | 'segmented' | 'none'
        """
        try:
            script = self.pm.load_script(project_name, script_file)
            return "generated", script
        except FileNotFoundError:
            project_dir = self.pm.get_project_path(project_name)
            try:
                safe_num = int(episode_num)
            except (ValueError, TypeError):
                return "none", None
            draft_filename = "step1_segments.md" if content_mode == "narration" else "step1_normalized_script.md"
            draft_file = project_dir / f"drafts/episode_{safe_num}/{draft_filename}"
            return ("segmented" if draft_file.exists() else "none"), None
        except ValueError as e:
            logger.warning(
                "劇本 JSON 損壞或路徑無效，跳過狀態計算 project=%s file=%s: %s",
                project_name,
                script_file,
                e,
            )
            return "generated", None

    @staticmethod
    def _has_structured_overview(project: dict) -> bool:
        overview = project.get("overview")
        if not isinstance(overview, dict):
            return False
        return any(str(overview.get(field) or "").strip() for field in OVERVIEW_FIELDS)

    @staticmethod
    def _sum_progress(episodes_stats: list[dict], key: str) -> tuple[int, int]:
        total = sum(s.get(key, {}).get("total", 0) for s in episodes_stats)
        completed = sum(s.get(key, {}).get("completed", 0) for s in episodes_stats)
        return total, completed

    def calculate_current_phase(
        self, project: dict, episodes_stats: list[dict], lorebook_completed: bool = True
    ) -> str:
        """根據專案和集狀態推斷當前階段"""
        if not self._has_structured_overview(project):
            return "setup"
        if not lorebook_completed:
            return "lorebook"
        if not episodes_stats:
            return "lorebook"
        any_generated = any(s["script_status"] == "generated" for s in episodes_stats)
        if not any_generated:
            return "lorebook"
        all_generated = all(s["script_status"] == "generated" for s in episodes_stats)
        if not all_generated:
            return "scripting"

        # 檢查分鏡圖完成率
        total_storyboards, completed_storyboards = self._sum_progress(episodes_stats, "storyboards")
        if total_storyboards > 0 and completed_storyboards < total_storyboards:
            return "storyboard"

        # 檢查影片完成率
        total_videos, completed_videos = self._sum_progress(episodes_stats, "videos")
        if total_videos > 0 and completed_videos < total_videos:
            return "video"

        return "completed"

    def _calculate_phase_progress(
        self, phase: str, episodes_stats: list[dict], lorebook_stats: dict | None = None
    ) -> float:
        """計算當前階段完成率 0.0–1.0"""
        if phase == "setup":
            return 0.0
        if phase == "lorebook":
            if not lorebook_stats:
                return 0.0
            chars_total = lorebook_stats.get("chars_total", 0)
            chars_done = lorebook_stats.get("chars_done", 0)
            clues_total = lorebook_stats.get("clues_total", 0)
            clues_done = lorebook_stats.get("clues_done", 0)
            scenes_total = lorebook_stats.get("scenes_total", 0)
            scenes_done = lorebook_stats.get("scenes_done", 0)

            total_assets = chars_total + clues_total + scenes_total
            done_assets = chars_done + clues_done + scenes_done
            return done_assets / total_assets if total_assets > 0 else 1.0
        if phase == "scripting":
            total = len(episodes_stats)
            if total == 0:
                return 0.0
            done = sum(1 for s in episodes_stats if s["script_status"] == "generated")
            return done / total
        if phase == "storyboard":
            total_storyboards, done_storyboards = self._sum_progress(episodes_stats, "storyboards")
            return done_storyboards / total_storyboards if total_storyboards > 0 else 0.0
        if phase == "video":
            total_videos, done_videos = self._sum_progress(episodes_stats, "videos")
            return done_videos / total_videos if total_videos > 0 else 0.0
        return 1.0  # completed

    @staticmethod
    def _make_fallback_ep_stats(script_status: str) -> dict:
        """構造未生成/無劇本集數的預設統計字典。"""
        return {
            "script_status": script_status,
            "status": "draft",
            "storyboards": {"total": 0, "completed": 0},
            "videos": {"total": 0, "completed": 0},
            "scenes_count": 0,
            "duration_seconds": 0,
        }

    def _build_episodes_stats(self, project_name: str, project: dict) -> list[dict]:
        """遍歷所有集數，載入劇本並計算每集統計。"""
        content_mode = project.get("content_mode", "narration")
        episodes_stats = []
        for ep in project.get("episodes", []):
            script_file = ep.get("script_file", "")
            episode_num = ep.get("episode", 0)

            if script_file:
                script_status, script = self._load_episode_script(
                    project_name, episode_num, script_file, content_mode=content_mode
                )
            else:
                script_status, script = "none", None

            if script_status == "generated" and script is not None:
                ep_stats = self.calculate_episode_stats(project_name, script)
                if ep_stats["status"] == "draft":
                    ep_stats["status"] = "scripted"
                ep_stats["script_status"] = "generated"
            else:
                ep_stats = self._make_fallback_ep_stats(script_status)
            episodes_stats.append(ep_stats)
        return episodes_stats

    def calculate_project_status(
        self, project_name: str, project: dict, *, _preloaded_episodes_stats: list[dict] | None = None
    ) -> dict:
        """
        計算專案整體狀態（用於列表 API）。

        Args:
            _preloaded_episodes_stats: 若已由 enrich_project 預先計算，直接傳入以避免重複 I/O。

        Returns:
            ProjectStatus 字典：current_phase, phase_progress, characters, clues, scenes, episodes_summary
        """
        project_dir = self.pm.get_project_path(project_name)

        # 角色統計
        chars = project.get("characters", {})
        chars_total = len(chars)
        chars_done = sum(1 for c in chars.values() if self._safe_exists(project_dir, c.get("character_sheet", "")))

        # 線索統計（所有線索，不限 major）
        clues = project.get("clues", {})
        clues_total = len(clues)
        clues_done = sum(1 for c in clues.values() if self._safe_exists(project_dir, c.get("clue_sheet", "")))

        # 場景統計
        scenes = project.get("scenes", {})
        scenes_total = len(scenes)
        scenes_done = sum(1 for s in scenes.values() if self._safe_exists(project_dir, s.get("scene_sheet", "")))

        # 每集狀態：優先使用預載入資料，否則自行載入
        if _preloaded_episodes_stats is not None:
            episodes_stats = _preloaded_episodes_stats
        else:
            episodes_stats = self._build_episodes_stats(project_name, project)

        lorebook_completed = chars_done == chars_total and clues_done == clues_total and scenes_done == scenes_total
        phase = self.calculate_current_phase(project, episodes_stats, lorebook_completed=lorebook_completed)

        lorebook_stats = {
            "chars_total": chars_total,
            "chars_done": chars_done,
            "clues_total": clues_total,
            "clues_done": clues_done,
            "scenes_total": scenes_total,
            "scenes_done": scenes_done,
        }
        phase_progress = self._calculate_phase_progress(phase, episodes_stats, lorebook_stats=lorebook_stats)

        return {
            "current_phase": phase,
            "phase_progress": phase_progress,
            "characters": {"total": chars_total, "completed": chars_done},
            "clues": {"total": clues_total, "completed": clues_done},
            "scenes": {"total": scenes_total, "completed": scenes_done},
            "episodes_summary": {
                "total": len(episodes_stats),
                "scripted": sum(1 for s in episodes_stats if s["script_status"] == "generated"),
                "in_production": sum(1 for s in episodes_stats if s["status"] == "in_production"),
                "completed": sum(1 for s in episodes_stats if s["status"] == "completed"),
            },
        }

    def enrich_project(self, project_name: str, project: dict) -> dict:
        """
        為專案資料注入所有計算欄位（用於詳情 API）。
        不修改原始 JSON 檔案，僅用於 API 響應。
        """
        # 計算每集明細（注入到 episode 物件）並收集統計
        episodes_stats = self._build_episodes_stats(project_name, project)

        for ep, ep_stats in zip(project.get("episodes", []), episodes_stats):
            ep.update(ep_stats)

        # 傳入預載入的 episodes_stats，避免 calculate_project_status 重複載入劇本
        project["status"] = self.calculate_project_status(
            project_name, project, _preloaded_episodes_stats=episodes_stats
        )
        return project

    def enrich_script(self, script: dict) -> dict:
        """
        為劇本資料注入計算欄位

        不會修改原始 JSON 檔案，僅用於 API 響應。

        Args:
            script: 原始劇本資料

        Returns:
            注入計算欄位後的劇本資料
        """
        content_mode, items = self._select_content_mode_and_items(script)
        script["content_mode"] = content_mode
        default_duration = 4 if content_mode == "narration" else 8

        total_duration = sum(i.get("duration_seconds", default_duration) for i in items)

        # 注入 metadata 計算欄位
        if "metadata" not in script:
            script["metadata"] = {}

        script["metadata"]["total_scenes"] = len(items)
        script["metadata"]["estimated_duration_seconds"] = total_duration
        script["duration_seconds"] = total_duration  # 讀時注入，與 metadata 保持同步

        # 聚合 characters_in_episode 和 clues_in_episode（僅用於 API 響應，不儲存）
        chars_set = set()
        clues_set = set()

        char_field = "characters_in_segment" if content_mode == "narration" else "characters_in_scene"
        clue_field = "clues_in_segment" if content_mode == "narration" else "clues_in_scene"

        for item in items:
            chars_set.update(item.get(char_field, []))
            clues_set.update(item.get(clue_field, []))

        script["characters_in_episode"] = sorted(chars_set)
        script["clues_in_episode"] = sorted(clues_set)

        return script
