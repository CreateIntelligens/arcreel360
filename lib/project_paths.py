"""
專案路徑解析

無狀態的專案路徑解析模組：依 projects_root 計算各類專案子路徑，
並提供專案名稱正規化、slug 生成與路徑遍歷防護等純函式工具。
"""

import os
import re
import secrets
import unicodedata
from pathlib import Path

PROJECT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9-]+$")
PROJECT_SLUG_SANITIZER = re.compile(r"[^a-zA-Z0-9]+")

PROJECT_FILE = "project.json"


def episode_final_filename(episode: int) -> str:
    """單集最終成片的確定性檔名（compose 輸出與前端讀取共用的命名契約）。"""
    return f"episode_{episode}_final.mp4"


class ProjectPaths:
    """無狀態的專案路徑解析器。

    僅依賴 projects_root 計算路徑，不持有任何可變狀態。
    """

    def __init__(self, projects_root: Path):
        self.projects_root = Path(projects_root)

    @staticmethod
    def normalize_project_name(name: str) -> str:
        """Validate and normalize a project identifier."""
        normalized = str(name).strip()
        if not normalized:
            raise ValueError("專案標識不能為空")
        if not PROJECT_NAME_PATTERN.fullmatch(normalized):
            raise ValueError("專案標識僅允許英文字母、數字和中劃線")
        return normalized

    @staticmethod
    def _slugify_project_title(title: str) -> str:
        """Build a filesystem-safe slug prefix from the project title."""
        ascii_text = unicodedata.normalize("NFKD", str(title).strip()).encode("ascii", "ignore").decode("ascii")
        slug = PROJECT_SLUG_SANITIZER.sub("-", ascii_text).strip("-_").lower()
        return slug[:24] or "project"

    def generate_project_name(self, title: str | None = None) -> str:
        """Generate a unique internal project identifier."""
        prefix = self._slugify_project_title(title or "")
        while True:
            candidate = f"{prefix}-{secrets.token_hex(4)}"
            if not (self.projects_root / candidate).exists():
                return candidate

    def get_project_path(self, name: str) -> Path:
        """獲取專案路徑（含路徑遍歷防護）"""
        name = self.normalize_project_name(name)
        real = os.path.realpath(self.projects_root / name)
        base = os.path.realpath(self.projects_root) + os.sep
        if not real.startswith(base):
            raise ValueError(f"非法專案名稱: '{name}'")
        project_dir = Path(real)
        if not project_dir.exists():
            raise FileNotFoundError(f"專案 '{name}' 不存在")
        return project_dir

    @staticmethod
    def _safe_subpath(base_dir: Path, filename: str) -> str:
        """校驗 filename 拼接後不逃出 base_dir，返回 realpath 字串。"""
        real = os.path.realpath(base_dir / filename)
        bound = os.path.realpath(base_dir) + os.sep
        if not real.startswith(bound):
            raise ValueError(f"非法檔名: '{filename}'")
        return real

    def _get_project_file_path(self, project_name: str) -> Path:
        """獲取專案後設資料檔案路徑"""
        return self.get_project_path(project_name) / PROJECT_FILE

    def get_source_path(self, project_name: str, filename: str) -> Path:
        """獲取原始檔路徑"""
        return self.get_project_path(project_name) / "source" / filename

    def get_character_path(self, project_name: str, filename: str) -> Path:
        """獲取角色設計圖路徑"""
        return self.get_project_path(project_name) / "characters" / filename

    def get_storyboard_path(self, project_name: str, filename: str) -> Path:
        """獲取分鏡圖片路徑"""
        return self.get_project_path(project_name) / "storyboards" / filename

    def get_video_path(self, project_name: str, filename: str) -> Path:
        """獲取影片路徑"""
        return self.get_project_path(project_name) / "videos" / filename

    def get_output_path(self, project_name: str, filename: str) -> Path:
        """獲取輸出路徑"""
        return self.get_project_path(project_name) / "output" / filename

    def get_clue_path(self, project_name: str, filename: str) -> Path:
        """獲取線索設計圖路徑"""
        return self.get_project_path(project_name) / "clues" / filename

    def get_scene_path(self, project_name: str, filename: str) -> Path:
        """獲取場景設計圖路徑"""
        return self.get_project_path(project_name) / "scenes" / filename
