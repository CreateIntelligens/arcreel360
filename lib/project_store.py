"""
專案 JSON 持久化引擎

封裝 project.json 的讀寫、原子寫入、檔案鎖與後設資料維護等純持久化操作。
依賴 ProjectPaths 解析檔案路徑，不持有其他可變狀態。
"""

import fcntl
import json
import os
import tempfile
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from lib.project_change_hints import emit_project_change_hint
from lib.project_paths import ProjectPaths


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ProjectStore:
    """專案後設資料（project.json）的持久化引擎。"""

    PROJECT_FILE = "project.json"

    def __init__(self, paths: ProjectPaths):
        self._paths = paths

    def project_exists(self, project_name: str) -> bool:
        """檢查專案後設資料檔案是否存在"""
        try:
            return self._paths._get_project_file_path(project_name).exists()
        except FileNotFoundError:
            return False

    def load_project(self, project_name: str) -> dict:
        """
        載入專案後設資料

        Args:
            project_name: 專案名稱

        Returns:
            專案後設資料字典
        """
        project_file = self._paths._get_project_file_path(project_name)

        if not project_file.exists():
            raise FileNotFoundError(f"專案後設資料檔案不存在: {project_file}")

        with open(project_file, encoding="utf-8") as f:
            return json.load(f)

    @contextmanager
    def _project_lock(self, project_name: str):
        """透過專用 lock file 獲取專案後設資料的排他鎖。

        使用獨立的 .project.json.lock 而非資料檔案本身，避免 os.replace
        更換 inode 後鎖失效的問題。
        """
        lock_path = self._paths._get_project_file_path(project_name).with_suffix(".lock")
        lock_path.touch(exist_ok=True)
        fd = open(lock_path)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            fd.close()

    @staticmethod
    def _atomic_write_json(path: Path, data: dict) -> None:
        """透過臨時檔案 + os.replace 原子寫入 JSON。"""
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(path.parent),
                prefix=".project.",
                suffix=".tmp",
                delete=False,
            ) as tmp:
                json.dump(data, tmp, ensure_ascii=False, indent=2)
                tmp_path = Path(tmp.name)
            os.replace(tmp_path, path)
            tmp_path = None
        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def save_project(self, project_name: str, project: dict) -> Path:
        """
        儲存專案後設資料

        Args:
            project_name: 專案名稱
            project: 專案後設資料字典

        Returns:
            儲存的檔案路徑
        """
        project_file = self._paths._get_project_file_path(project_name)

        self._touch_metadata(project)

        with self._project_lock(project_name):
            self._atomic_write_json(project_file, project)

        emit_project_change_hint(
            project_name,
            changed_paths=[self.PROJECT_FILE],
        )

        return project_file

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
        project_file = self._paths._get_project_file_path(project_name)

        with self._project_lock(project_name):
            with open(project_file, encoding="utf-8") as f:
                project = json.load(f)
            mutate_fn(project)
            self._touch_metadata(project)
            self._atomic_write_json(project_file, project)

        emit_project_change_hint(
            project_name,
            changed_paths=[self.PROJECT_FILE],
        )

        return project_file

    @staticmethod
    def _touch_metadata(project: dict) -> None:
        now = _utc_now_iso()
        if "metadata" not in project:
            project["metadata"] = {"created_at": now, "updated_at": now}
        else:
            project["metadata"]["updated_at"] = now

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
        project_name = self._paths.normalize_project_name(project_name)
        project_title = str(title).strip() if title is not None else ""

        project = {
            "title": project_title or project_name,
            "content_mode": content_mode,
            "aspect_ratio": aspect_ratio,
            "style": style or "",
            "episodes": [],
            "characters": {},
            "clues": {},
            "metadata": {
                "created_at": _utc_now_iso(),
                "updated_at": _utc_now_iso(),
            },
        }
        if default_duration is not None:
            project["default_duration"] = default_duration

        self.save_project(project_name, project)
        return project
