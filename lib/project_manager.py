"""
專案檔案管理器

管理影片專案的目錄結構、分鏡劇本讀寫、狀態追蹤。
"""

import logging
import os
import re
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from lib import overview_generator
from lib.project_paths import ProjectPaths
from lib.project_store import ProjectStore
from lib.script_repository import ScriptRepository
from lib.symlink_repair import repair_all_symlinks, repair_claude_symlink

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


# ==================== 資料模型 ====================


class ProjectOverview(BaseModel):
    """專案概述資料模型，用於 Gemini Structured Outputs"""

    synopsis: str = Field(description="故事梗概，200-300字，概括主線劇情")
    genre: str = Field(description="題材型別，如：古裝宮鬥、現代懸疑、玄幻修仙")
    theme: str = Field(description="核心主題，如：復仇與救贖、成長與蛻變")
    world_setting: str = Field(description="時代背景和世界觀設定，100-200字")


class ProjectManager:
    """影片專案管理器"""

    # 專案子目錄結構
    SUBDIRS = [
        "source",
        "scripts",
        "drafts",
        "characters",
        "clues",
        "scenes",
        "storyboards",
        "videos",
        "thumbnails",
        "output",
    ]

    # 專案後設資料檔名
    PROJECT_FILE = "project.json"

    @staticmethod
    def normalize_project_name(name: str) -> str:
        """Validate and normalize a project identifier."""
        return ProjectPaths.normalize_project_name(name)

    @staticmethod
    def _slugify_project_title(title: str) -> str:
        """Build a filesystem-safe slug prefix from the project title."""
        return ProjectPaths._slugify_project_title(title)

    def generate_project_name(self, title: str | None = None) -> str:
        """Generate a unique internal project identifier."""
        return self._paths.generate_project_name(title)

    @classmethod
    def from_cwd(cls) -> tuple["ProjectManager", str]:
        """從當前工作目錄推斷 ProjectManager 和專案名稱。

        假定 cwd 為 ``projects/{project_name}/`` 格式。
        返回 ``(ProjectManager, project_name)`` 元組。
        """
        cwd = Path.cwd().resolve()
        project_name = cwd.name
        projects_root = cwd.parent
        pm = cls(projects_root)
        if not (projects_root / project_name / cls.PROJECT_FILE).exists():
            raise FileNotFoundError(f"當前目錄不是有效的專案目錄: {cwd}")
        return pm, project_name

    @staticmethod
    def _scene_entry(description: str, scene_sheet: str = "") -> dict:
        return {
            "description": description,
            "scene_sheet": scene_sheet,
            "scene_ref": "",
        }

    @staticmethod
    def _needs_generated_sheet(project_dir: Path, entity: dict, sheet_key: str) -> bool:
        # 已有 sheet（含使用者上傳寫入 v0 後指向的 sheet）即不需 AI 生成
        sheet = entity.get(sheet_key)
        return not sheet or not (project_dir / sheet).exists()

    def __init__(self, projects_root: str | None = None):
        """
        初始化專案管理器

        Args:
            projects_root: 專案根目錄，預設為當前目錄下的 projects/
        """
        if projects_root is None:
            # 嘗試從環境變數或預設路徑獲取
            projects_root = os.environ.get("AI_ANIME_PROJECTS", "projects")

        self.projects_root = Path(projects_root)
        self.projects_root.mkdir(parents=True, exist_ok=True)
        self._paths = ProjectPaths(self.projects_root)
        self._store = ProjectStore(self._paths)
        self._scripts = ScriptRepository(
            paths=self._paths,
            store=self._store,
            sync_characters=lambda project_name, script_filename: getattr(
                self,
                "sync_characters_from_script",
                lambda *_args: None,
            )(project_name, script_filename),
            sync_clues=lambda project_name, script_filename: getattr(
                self,
                "sync_clues_from_script",
                lambda *_args: None,
            )(project_name, script_filename),
        )

        from lib.lorebook_manager import LorebookManager

        self.lorebook = LorebookManager(self)

        from lib.episode_manager import EpisodeManager

        self.episode_manager = EpisodeManager(self)

    def list_projects(self) -> list[str]:
        """列出所有專案"""
        return [d.name for d in self.projects_root.iterdir() if d.is_dir() and not d.name.startswith(".")]

    def create_project(self, name: str) -> Path:
        """
        建立新專案

        Args:
            name: 專案標識（全域性唯一，用於 URL 和檔案系統）

        Returns:
            專案目錄路徑
        """
        name = self.normalize_project_name(name)
        project_dir = self.projects_root / name

        if project_dir.exists():
            raise FileExistsError(f"專案 '{name}' 已存在")

        # 建立所有子目錄
        for subdir in self.SUBDIRS:
            (project_dir / subdir).mkdir(parents=True, exist_ok=True)

        self.repair_claude_symlink(project_dir)

        return project_dir

    def repair_claude_symlink(self, project_dir: Path) -> dict:
        return repair_claude_symlink(project_dir, profile_root=self.projects_root.parent)

    def repair_all_symlinks(self) -> dict:
        return repair_all_symlinks(self.projects_root)

    def get_project_path(self, name: str) -> Path:
        """獲取專案路徑（含路徑遍歷防護）"""
        return self._paths.get_project_path(name)

    @staticmethod
    def _safe_subpath(base_dir: Path, filename: str) -> str:
        """校驗 filename 拼接後不逃出 base_dir，返回 realpath 字串。"""
        return ProjectPaths._safe_subpath(base_dir, filename)

    def get_project_status(self, name: str) -> dict[str, Any]:
        """
        獲取專案狀態

        Returns:
            包含各階段完成情況的字典
        """
        project_dir = self.get_project_path(name)

        status = {
            "name": name,
            "path": str(project_dir),
            "source_files": [],
            "scripts": [],
            "characters": [],
            "clues": [],
            "storyboards": [],
            "videos": [],
            "outputs": [],
            "current_stage": "empty",
        }

        # 檢查各目錄內容
        for subdir in self.SUBDIRS:
            subdir_path = project_dir / subdir
            if subdir_path.exists():
                files = list(subdir_path.glob("*"))
                if subdir == "source":
                    status["source_files"] = [f.name for f in files if f.is_file()]
                elif subdir == "scripts":
                    status["scripts"] = [f.name for f in files if f.suffix == ".json"]
                elif subdir == "characters":
                    status["characters"] = [f.name for f in files if f.suffix in [".png", ".jpg", ".jpeg"]]
                elif subdir == "clues":
                    status["clues"] = [f.name for f in files if f.suffix in [".png", ".jpg", ".jpeg"]]
                elif subdir == "storyboards":
                    status["storyboards"] = [f.name for f in files if f.suffix in [".png", ".jpg", ".jpeg"]]
                elif subdir == "videos":
                    status["videos"] = [f.name for f in files if f.suffix in [".mp4", ".webm"]]
                elif subdir == "output":
                    status["outputs"] = [f.name for f in files if f.suffix in [".mp4", ".webm"]]

        # 確定當前階段
        if status["outputs"]:
            status["current_stage"] = "completed"
        elif status["videos"]:
            status["current_stage"] = "videos_generated"
        elif status["storyboards"]:
            status["current_stage"] = "storyboards_generated"
        elif status["characters"]:
            status["current_stage"] = "characters_generated"
        elif status["scripts"]:
            status["current_stage"] = "script_created"
        elif status["source_files"]:
            status["current_stage"] = "source_ready"
        else:
            status["current_stage"] = "empty"

        return status

    # ==================== 分鏡劇本操作 ====================

    def create_script(self, project_name: str, title: str, chapter: str) -> dict:
        return self._scripts.create_script(project_name, title, chapter)

    def save_script(self, project_name: str, script: dict, filename: str | None = None) -> Path:
        return self._scripts.save_script(project_name, script, filename)

    def sync_episode_from_script(self, project_name: str, script_filename: str) -> dict:
        return self._scripts.sync_episode_from_script(project_name, script_filename)

    def load_script(self, project_name: str, filename: str) -> dict:
        return self._scripts.load_script(project_name, filename)

    def list_scripts(self, project_name: str) -> list[str]:
        return self._scripts.list_scripts(project_name)

    def update_character_sheet(self, project_name: str, script_filename: str, name: str, sheet_path: str) -> dict:
        return self._scripts.update_character_sheet(project_name, script_filename, name, sheet_path)

    @staticmethod
    def create_generated_assets(content_mode: str = "narration") -> dict:
        return ScriptRepository.create_generated_assets(content_mode)

    @staticmethod
    def create_scene_template(scene_id: str, episode: int = 1, duration_seconds: int = 8) -> dict:
        return ScriptRepository.create_scene_template(scene_id, episode, duration_seconds)

    def normalize_scene(self, scene: dict, episode: int = 1) -> dict:
        return self._scripts.normalize_scene(scene, episode)

    def update_scene_status(self, scene: dict) -> str:
        return self._scripts.update_scene_status(scene)

    def normalize_script(self, project_name: str, script_filename: str, save: bool = True) -> dict:
        return self._scripts.normalize_script(project_name, script_filename, save)

    def add_scene(self, project_name: str, script_filename: str, scene: dict) -> dict:
        return self._scripts.add_scene(project_name, script_filename, scene)

    def update_scene_asset(
        self,
        project_name: str,
        script_filename: str,
        scene_id: str,
        asset_type: str,
        asset_path: str,
    ) -> dict:
        return self._scripts.update_scene_asset(project_name, script_filename, scene_id, asset_type, asset_path)

    def update_scene_backend(
        self,
        project_name: str,
        script_filename: str,
        scene_id: str,
        *,
        image_backend: str | None | _BackendUnset = _BACKEND_UNSET,
        video_backend: str | None | _BackendUnset = _BACKEND_UNSET,
    ) -> dict:
        kwargs: dict[str, str | None] = {}
        if image_backend is not _BACKEND_UNSET:
            kwargs["image_backend"] = image_backend
        if video_backend is not _BACKEND_UNSET:
            kwargs["video_backend"] = video_backend
        return self._scripts.update_scene_backend(project_name, script_filename, scene_id, **kwargs)

    def get_pending_scenes(self, project_name: str, script_filename: str, asset_type: str) -> list[dict]:
        return self._scripts.get_pending_scenes(project_name, script_filename, asset_type)

    def get_scenes_needing_storyboard(self, project_name: str, script_filename: str) -> list[dict]:
        return self._scripts.get_scenes_needing_storyboard(project_name, script_filename)

    # ==================== 檔案路徑工具 ====================

    def get_source_path(self, project_name: str, filename: str) -> Path:
        """獲取原始檔路徑"""
        return self._paths.get_source_path(project_name, filename)

    def get_character_path(self, project_name: str, filename: str) -> Path:
        """獲取角色設計圖路徑"""
        return self._paths.get_character_path(project_name, filename)

    def get_storyboard_path(self, project_name: str, filename: str) -> Path:
        """獲取分鏡圖片路徑"""
        return self._paths.get_storyboard_path(project_name, filename)

    def get_video_path(self, project_name: str, filename: str) -> Path:
        """獲取影片路徑"""
        return self._paths.get_video_path(project_name, filename)

    def get_output_path(self, project_name: str, filename: str) -> Path:
        """獲取輸出路徑"""
        return self._paths.get_output_path(project_name, filename)

    # ==================== 專案級後設資料管理 ====================

    def _get_project_file_path(self, project_name: str) -> Path:
        """獲取專案後設資料檔案路徑"""
        return self._paths._get_project_file_path(project_name)

    def project_exists(self, project_name: str) -> bool:
        """檢查專案後設資料檔案是否存在"""
        return self._store.project_exists(project_name)

    def load_project(self, project_name: str) -> dict:
        """
        載入專案後設資料

        Args:
            project_name: 專案名稱

        Returns:
            專案後設資料字典
        """
        return self._store.load_project(project_name)

    @contextmanager
    def _project_lock(self, project_name: str):
        """透過專用 lock file 獲取專案後設資料的排他鎖（委派給 ProjectStore）。"""
        with self._store._project_lock(project_name):
            yield

    @staticmethod
    def _atomic_write_json(path: Path, data: dict) -> None:
        """透過臨時檔案 + os.replace 原子寫入 JSON（委派給 ProjectStore）。"""
        ProjectStore._atomic_write_json(path, data)

    def save_project(self, project_name: str, project: dict) -> Path:
        """
        儲存專案後設資料

        Args:
            project_name: 專案名稱
            project: 專案後設資料字典

        Returns:
            儲存的檔案路徑
        """
        return self._store.save_project(project_name, project)

    def update_project(
        self,
        project_name: str,
        mutate_fn: Callable[[dict], None],
    ) -> Path:
        """原子性地更新 project.json：加檔案鎖 → 讀 → 修改 → 原子寫回。

        避免併發任務（如同時生成多張角色圖片）之間的 lost-update 競態。

        Args:
            project_name: 專案名稱
            mutate_fn: 接收 project dict 並就地修改的回撥函式
        """
        return self._store.update_project(project_name, mutate_fn)

    @staticmethod
    def _touch_metadata(project: dict) -> None:
        ProjectStore._touch_metadata(project)

    def create_project_metadata(
        self,
        project_name: str,
        title: str | None = None,
        style: str | None = None,
        content_mode: str = "narration",
        aspect_ratio: str = "9:16",
        default_duration: int | None = None,
    ) -> dict:
        """
        建立新的專案後設資料檔案

        Args:
            project_name: 專案標識
            title: 專案標題，留空時預設使用專案標識
            style: 整體視覺風格描述
            content_mode: 內容模式 ('narration' 或 'drama')
            aspect_ratio: 影片寬高比（獨立於 content_mode）
            default_duration: 預設影片時長（秒），None 表示使用系統預設值

        Returns:
            專案後設資料字典
        """
        return self._store.create_project_metadata(
            project_name,
            title=title,
            style=style,
            content_mode=content_mode,
            aspect_ratio=aspect_ratio,
            default_duration=default_duration,
        )

    def add_episode(self, project_name: str, episode: int, title: str, script_file: str) -> dict:
        """
        向專案新增劇集

        Args:
            project_name: 專案名稱
            episode: 集數
            title: 劇集標題
            script_file: 劇本檔案相對路徑

        Returns:
            更新後的專案後設資料
        """
        project = self.load_project(project_name)

        # 檢查是否已存在
        for ep in project["episodes"]:
            if ep["episode"] == episode:
                ep["title"] = title
                ep["script_file"] = script_file
                self.save_project(project_name, project)
                return project

        # 新增新劇集（不包含統計欄位，由 StatusCalculator 讀時計算）
        next_order = _next_display_order(project["episodes"])
        project["episodes"].append(
            {"episode": episode, "title": title, "script_file": script_file, "order": next_order}
        )

        # 按集數排序（陣列物理順序仍以集數遞增，顯示順序由 order 欄位決定）
        project["episodes"].sort(key=lambda x: x["episode"])

        self.save_project(project_name, project)
        return project

    def reorder_episodes(self, project_name: str, ordered_episode_numbers: list[int]) -> dict:
        """依指定的集數順序重設每個 episode 的 ``order`` 欄位。

        Args:
            project_name: 專案名稱
            ordered_episode_numbers: 期望的顯示順序（用集數編號表示）。
                必須與專案現存集數恰好相同（同集合、同個數，不能多也不能少）。

        Returns:
            更新後的 project 字典。

        Raises:
            ValueError: 傳入集數與現存不匹配（缺漏、多餘或重複）。
        """
        project = self.load_project(project_name)
        episodes = project.get("episodes", [])
        existing = [int(ep.get("episode", -1)) for ep in episodes]
        requested = [int(n) for n in ordered_episode_numbers]
        if sorted(existing) != sorted(requested):
            raise ValueError(f"傳入的集數與現存劇集不一致：現存 {sorted(existing)}，傳入 {sorted(requested)}")
        if len(set(requested)) != len(requested):
            raise ValueError(f"傳入的集數有重複：{requested}")

        order_map = {ep_num: idx for idx, ep_num in enumerate(requested)}
        for ep in episodes:
            ep["order"] = order_map[int(ep.get("episode"))]

        self.save_project(project_name, project)
        return project

    def remove_episode(self, project_name: str, episode: int) -> tuple[dict, list[str]]:
        """[已委託] 從專案移除一整集。"""
        return self.episode_manager.remove_episode(project_name, episode)

    def commit_episode_split(
        self,
        project_name: str,
        source_rel: str,
        episode: int,
        part_before: str,
        part_after: str,
        title: str | None = None,
    ) -> dict:
        """[已委託] 落地一次分集切分。"""
        return self.episode_manager.commit_episode_split(
            project_name, source_rel, episode, part_before, part_after, title
        )

    def sync_project_status(self, project_name: str) -> dict:
        """
        [已廢棄] 同步專案狀態

        此方法已廢棄。status、progress、scenes_count 等統計欄位
        現在由 StatusCalculator 讀時計算，不再儲存在 JSON 檔案中。

        保留此方法僅為向後相容，實際不執行任何寫入操作。

        Args:
            project_name: 專案名稱

        Returns:
            專案後設資料（不含統計欄位，統計欄位由 StatusCalculator 注入）
        """
        import warnings

        warnings.warn(
            "sync_project_status() 已廢棄。status 等統計欄位現由 StatusCalculator 讀時計算。",
            DeprecationWarning,
            stacklevel=2,
        )
        # 僅返回專案資料，不執行任何寫入
        return self.load_project(project_name)

    # ==================== 專案級角色管理 ====================

    def add_project_character(
        self,
        project_name: str,
        name: str,
        description: str,
        voice_style: str | None = None,
        character_sheet: str | None = None,
    ) -> dict:
        return self.lorebook.add_project_character(project_name, name, description, voice_style, character_sheet)

    def update_project_character_sheet(self, project_name: str, name: str, sheet_path: str) -> dict:
        return self.lorebook.update_project_character_sheet(project_name, name, sheet_path)

    def update_character_reference_image(self, project_name: str, char_name: str, ref_path: str) -> dict:
        return self.lorebook.update_character_reference_image(project_name, char_name, ref_path)

    def get_project_character(self, project_name: str, name: str) -> dict:
        return self.lorebook.get_project_character(project_name, name)

    # ==================== 線索管理 ====================

    def update_clue_sheet(self, project_name: str, name: str, sheet_path: str) -> dict:
        return self.lorebook.update_clue_sheet(project_name, name, sheet_path)

    def get_clue(self, project_name: str, name: str) -> dict:
        return self.lorebook.get_clue(project_name, name)

    def get_pending_characters(self, project_name: str) -> list[dict]:
        return self.lorebook.get_pending_characters(project_name)

    def get_pending_clues(self, project_name: str) -> list[dict]:
        return self.lorebook.get_pending_clues(project_name)

    def get_clue_path(self, project_name: str, filename: str) -> Path:
        return self.lorebook.get_clue_path(project_name, filename)

    # ==================== 角色/線索直接寫入工具 ====================

    def add_character(self, project_name: str, name: str, description: str, voice_style: str = "") -> bool:
        return self.lorebook.add_character(project_name, name, description, voice_style)

    def add_clue(
        self,
        project_name: str,
        name: str,
        description: str,
        importance: str = "minor",
    ) -> bool:
        return self.lorebook.add_clue(project_name, name, description, importance)

    def add_characters_batch(self, project_name: str, characters: dict[str, dict]) -> int:
        return self.lorebook.add_characters_batch(project_name, characters)

    def add_clues_batch(self, project_name: str, clues: dict[str, dict]) -> int:
        return self.lorebook.add_clues_batch(project_name, clues)

    # ==================== 參考圖收集工具 ====================

    def collect_reference_images(self, project_name: str, scene: dict) -> list[Path]:
        return self.lorebook.collect_reference_images(project_name, scene)

    # ==================== 場景管理 ====================

    def add_project_scene(
        self,
        project_name: str,
        name: str,
        description: str,
        scene_sheet: str | None = None,
    ) -> dict:
        return self.lorebook.add_project_scene(project_name, name, description, scene_sheet)

    def update_scene_sheet(self, project_name: str, name: str, sheet_path: str) -> dict:
        return self.lorebook.update_scene_sheet(project_name, name, sheet_path)

    def update_scene_reference_image(self, project_name: str, name: str, ref_path: str) -> dict:
        return self.lorebook.update_scene_reference_image(project_name, name, ref_path)

    def get_project_scene(self, project_name: str, name: str) -> dict:
        return self.lorebook.get_project_scene(project_name, name)

    def get_scene_path(self, project_name: str, filename: str) -> Path:
        return self.lorebook.get_scene_path(project_name, filename)

    def get_pending_scene_sheets(self, project_name: str) -> list[dict]:
        return self.lorebook.get_pending_scene_sheets(project_name)

    def add_scenes_batch(self, project_name: str, scenes: dict[str, dict]) -> int:
        return self.lorebook.add_scenes_batch(project_name, scenes)

    def update_clue_reference_image(self, project_name: str, name: str, ref_path: str) -> dict:
        return self.lorebook.update_clue_reference_image(project_name, name, ref_path)

    def _find_script_filename_by_scene_id(self, project_name: str, scene_id: str) -> str:
        return self._scripts._find_script_filename_by_scene_id(project_name, scene_id)

    def update_storyboard_reference_image(self, project_name: str, name: str, ref_path: str) -> dict:
        return self._scripts.update_storyboard_reference_image(project_name, name, ref_path)

    def update_storyboard_sheet(self, project_name: str, name: str, sheet_path: str) -> dict:
        return self._scripts.update_storyboard_sheet(project_name, name, sheet_path)

    def _update_storyboard_item_field(self, project_name: str, name: str, field: str, value: str) -> dict:
        return self._scripts._update_storyboard_item_field(project_name, name, field, value)

    # ==================== 專案概述生成 ====================

    def _read_source_files(self, project_name: str, max_chars: int = 50000) -> str:
        return overview_generator._read_source_files(self._paths, project_name, max_chars)

    async def generate_overview(
        self,
        project_name: str,
        *,
        model: str | None = None,
        instruction: str | None = None,
    ) -> dict:
        return await overview_generator.generate_overview(
            self._store,
            self._paths,
            project_name,
            model=model,
            instruction=instruction,
        )
