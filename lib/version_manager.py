"""
版本管理模組

管理分鏡圖、影片、角色圖、線索圖的歷史版本。
支援版本備份、切換當前版本、記錄和查詢。
"""

import json
import shutil
import threading
from datetime import UTC, datetime
from pathlib import Path

_LOCKS_GUARD = threading.Lock()
_LOCKS_BY_VERSIONS_FILE: dict[str, threading.RLock] = {}


def _get_versions_file_lock(versions_file: Path) -> threading.RLock:
    key = str(Path(versions_file).resolve())
    with _LOCKS_GUARD:
        lock = _LOCKS_BY_VERSIONS_FILE.get(key)
        if lock is None:
            lock = threading.RLock()
            _LOCKS_BY_VERSIONS_FILE[key] = lock
        return lock


class VersionManager:
    """版本管理器"""

    # 支援的資源型別
    RESOURCE_TYPES = ("storyboards", "videos", "characters", "clues", "scenes", "output")

    # 資源型別對應的副檔名
    EXTENSIONS = {
        "storyboards": ".png",
        "videos": ".mp4",
        "characters": ".png",
        "clues": ".png",
        "scenes": ".png",
        "output": ".mp4",
    }

    # v0 = 使用者上傳的可替換基底版本（與 v1+ 的不可變 AI 歷史快照語義不同）
    BASE_VERSION = 0

    def __init__(self, project_path: Path):
        """
        初始化版本管理器

        Args:
            project_path: 專案根目錄路徑
        """
        self.project_path = Path(project_path)
        self.versions_dir = self.project_path / "versions"
        self.versions_file = self.versions_dir / "versions.json"
        self._lock = _get_versions_file_lock(self.versions_file)

        # 確保版本目錄存在
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        """確保版本目錄結構存在"""
        self.versions_dir.mkdir(parents=True, exist_ok=True)
        for resource_type in self.RESOURCE_TYPES:
            (self.versions_dir / resource_type).mkdir(exist_ok=True)

    def _load_versions(self) -> dict:
        """載入版本後設資料"""
        if not self.versions_file.exists():
            return {rt: {} for rt in self.RESOURCE_TYPES}

        with open(self.versions_file, encoding="utf-8") as f:
            return json.load(f)

    def _save_versions(self, data: dict) -> None:
        """儲存版本後設資料"""
        with open(self.versions_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _generate_timestamp(self) -> str:
        """生成時間戳字串（用於檔名，採 UTC 確保跨時區可排序）"""
        return datetime.now(UTC).strftime("%Y%m%dT%H%M%S")

    def _generate_iso_timestamp(self) -> str:
        """生成 ISO 格式時間戳（用於後設資料）"""
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def get_versions(self, resource_type: str, resource_id: str) -> dict:
        """
        獲取資源的所有版本資訊

        Args:
            resource_type: 資源型別 (storyboards, videos, characters, clues)
            resource_id: 資源 ID (如 E1S01, 姜月茴)

        Returns:
            版本資訊字典，包含 current_version 和 versions 列表
        """
        if resource_type not in self.RESOURCE_TYPES:
            raise ValueError(f"不支援的資源型別: {resource_type}")

        with self._lock:
            data = self._load_versions()
            resource_data = data.get(resource_type, {}).get(resource_id)

            if not resource_data:
                return {"current_version": 0, "versions": []}

            # 新增 is_current 和 file_url 欄位；v0 排在最前，其餘按版本號升序
            versions = []
            for v in sorted(resource_data.get("versions", []), key=lambda x: x.get("version", 0)):
                version_info = v.copy()
                version_info["is_current"] = v["version"] == resource_data["current_version"]
                version_info["file_url"] = f"/api/v1/files/{self.project_path.name}/{v['file']}"
                versions.append(version_info)

            return {"current_version": resource_data.get("current_version", 0), "versions": versions}

    def get_current_version(self, resource_type: str, resource_id: str) -> int:
        """
        獲取當前版本號

        Args:
            resource_type: 資源型別
            resource_id: 資源 ID

        Returns:
            當前版本號，無版本時返回 0
        """
        info = self.get_versions(resource_type, resource_id)
        return info["current_version"]

    def add_version(
        self, resource_type: str, resource_id: str, prompt: str, source_file: Path | None = None, **metadata
    ) -> int:
        """
        新增新版本記錄

        Args:
            resource_type: 資源型別
            resource_id: 資源 ID
            prompt: 生成該版本使用的 prompt
            source_file: 原始檔路徑（用於複製到版本目錄）
            **metadata: 額外的後設資料（如 aspect_ratio, duration_seconds）

        Returns:
            新版本號
        """
        if resource_type not in self.RESOURCE_TYPES:
            raise ValueError(f"不支援的資源型別: {resource_type}")

        with self._lock:
            data = self._load_versions()

            # 確保資源型別存在
            if resource_type not in data:
                data[resource_type] = {}

            # 獲取或建立資源記錄
            if resource_id not in data[resource_type]:
                data[resource_type][resource_id] = {"current_version": 0, "versions": []}

            resource_data = data[resource_type][resource_id]
            existing_versions = resource_data.get("versions", [])
            # AI 生成版本從 1 起算；v0（使用者上傳基底）不參與遞增
            max_version = max(
                (item.get("version", 0) for item in existing_versions if item.get("version", 0) > 0),
                default=0,
            )
            new_version = max_version + 1

            # 生成版本檔名和路徑
            timestamp = self._generate_timestamp()
            ext = self.EXTENSIONS.get(resource_type, ".png")
            version_filename = f"{resource_id}_v{new_version}_{timestamp}{ext}"
            version_rel_path = f"versions/{resource_type}/{version_filename}"
            version_abs_path = self.project_path / version_rel_path

            # 如果有原始檔，複製到版本目錄
            if source_file and Path(source_file).exists():
                shutil.copy2(source_file, version_abs_path)

            # 建立版本記錄
            version_record = {
                "version": new_version,
                "file": version_rel_path,
                "prompt": prompt,
                "created_at": self._generate_iso_timestamp(),
                **metadata,
            }

            resource_data["versions"].append(version_record)
            resource_data["current_version"] = new_version

            self._save_versions(data)
            return new_version

    def set_base_version(
        self,
        resource_type: str,
        resource_id: str,
        source_file: Path,
        prompt: str = "使用者上傳",
        **metadata,
    ) -> dict:
        """寫入 / 覆蓋 v0 基底版本（使用者上傳的可替換基底）。

        與 add_version 不同：v0 是固定槽位，重複呼叫會覆蓋同一筆而非累積，
        且不影響 AI 版本（v1+）的遞增。寫入後 current_version 設為 0。
        """
        if resource_type not in self.RESOURCE_TYPES:
            raise ValueError(f"不支援的資源型別: {resource_type}")

        source_file = Path(source_file)
        if not source_file.exists():
            raise FileNotFoundError(f"來源檔案不存在: {source_file}")

        with self._lock:
            data = self._load_versions()
            data.setdefault(resource_type, {})
            resource_data = data[resource_type].setdefault(resource_id, {"current_version": 0, "versions": []})

            # v0 檔名固定（不帶 timestamp）以確保覆蓋而非累積
            ext = self.EXTENSIONS.get(resource_type, ".png")
            version_filename = f"{resource_id}_v0{ext}"
            version_rel_path = f"versions/{resource_type}/{version_filename}"
            version_abs_path = self.project_path / version_rel_path
            version_abs_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, version_abs_path)

            base_record = {
                "version": self.BASE_VERSION,
                "file": version_rel_path,
                "prompt": prompt,
                "created_at": self._generate_iso_timestamp(),
                **metadata,
            }

            versions = resource_data.setdefault("versions", [])
            for idx, item in enumerate(versions):
                if item.get("version") == self.BASE_VERSION:
                    versions[idx] = base_record
                    break
            else:
                versions.append(base_record)

            resource_data["current_version"] = self.BASE_VERSION
            self._save_versions(data)

        return {"version": self.BASE_VERSION, "file": version_rel_path}

    def remove_base_version(self, resource_type: str, resource_id: str) -> None:
        """移除 v0 基底版本，包括 versions.json 裡的記錄與磁碟上的實體 v0 檔案。

        若 current_version 當時是 0，則重新計算為最新 AI 版本，若無其他版本則設為 0。
        """
        if resource_type not in self.RESOURCE_TYPES:
            raise ValueError(f"不支援的資源型別: {resource_type}")

        with self._lock:
            data = self._load_versions()
            if resource_type not in data or resource_id not in data[resource_type]:
                return

            resource_data = data[resource_type][resource_id]
            versions = resource_data.get("versions", [])

            # 尋找 version == 0 的記錄並移除
            v0_record = None
            new_versions = []
            for v in versions:
                if v.get("version") == self.BASE_VERSION:
                    v0_record = v
                else:
                    new_versions.append(v)

            if v0_record:
                # 刪除實體檔案
                v0_file = self.project_path / v0_record["file"]
                if v0_file.exists():
                    v0_file.unlink()

                # 更新 versions 列表
                resource_data["versions"] = new_versions

                # 重新計算 current_version
                if resource_data.get("current_version") == self.BASE_VERSION:
                    if new_versions:
                        resource_data["current_version"] = max(item.get("version", 0) for item in new_versions)
                    else:
                        resource_data["current_version"] = 0

                # 若 versions 為空且 current_version 為 0，則移除該項以保持乾淨
                if not resource_data["versions"] and resource_data["current_version"] == 0:
                    del data[resource_type][resource_id]

                self._save_versions(data)

    def backup_current(
        self, resource_type: str, resource_id: str, current_file: Path, prompt: str, **metadata
    ) -> int | None:
        """
        將當前檔案備份到版本目錄

        如果當前檔案不存在，不執行任何操作。

        Args:
            resource_type: 資源型別
            resource_id: 資源 ID
            current_file: 當前檔案路徑
            prompt: 當前版本的 prompt
            **metadata: 額外的後設資料

        Returns:
            備份的版本號，如果未備份則返回 None
        """
        current_file = Path(current_file)
        if not current_file.exists():
            return None

        return self.add_version(
            resource_type=resource_type, resource_id=resource_id, prompt=prompt, source_file=current_file, **metadata
        )

    def ensure_current_tracked(
        self, resource_type: str, resource_id: str, current_file: Path, prompt: str, **metadata
    ) -> int | None:
        """
        確保“當前檔案”至少有一個版本記錄

        用於升級/遷移場景：磁碟上已有 current_file，但 versions.json 還沒有記錄。
        若該資源已存在版本記錄（current_version > 0）則不會重複寫入。

        Args:
            resource_type: 資源型別
            resource_id: 資源 ID
            current_file: 當前檔案路徑
            prompt: 當前檔案對應的 prompt（用於記錄）
            **metadata: 額外後設資料

        Returns:
            新增的版本號；若無需新增或檔案不存在則返回 None
        """
        current_file = Path(current_file)
        if not current_file.exists():
            return None

        if resource_type not in self.RESOURCE_TYPES:
            raise ValueError(f"不支援的資源型別: {resource_type}")

        with self._lock:
            if self.get_current_version(resource_type, resource_id) > 0:
                return None
            return self.add_version(
                resource_type=resource_type,
                resource_id=resource_id,
                prompt=prompt,
                source_file=current_file,
                **metadata,
            )

    def restore_version(self, resource_type: str, resource_id: str, version: int, current_file: Path) -> dict:
        """
        切換到指定版本

        將指定版本複製到當前路徑，並將 current_version 指向該版本。

        Args:
            resource_type: 資源型別
            resource_id: 資源 ID
            version: 要還原的版本號
            current_file: 當前檔案路徑

        Returns:
            切換資訊，包含 restored_version, current_version, prompt
        """
        if resource_type not in self.RESOURCE_TYPES:
            raise ValueError(f"不支援的資源型別: {resource_type}")

        current_file = Path(current_file)

        with self._lock:
            data = self._load_versions()
            resource_data = data.get(resource_type, {}).get(resource_id)

            if not resource_data:
                raise ValueError(f"資源不存在: {resource_type}/{resource_id}")

            target_version = None
            for v in resource_data["versions"]:
                if v["version"] == version:
                    target_version = v
                    break

            if not target_version:
                raise ValueError(f"版本不存在: {version}")

            target_file = self.project_path / target_version["file"]
            if not target_file.exists():
                raise FileNotFoundError(f"版本檔案不存在: {target_file}")

            current_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target_file, current_file)

            resource_data["current_version"] = version
            self._save_versions(data)

        restored_prompt = target_version.get("prompt", "")
        return {
            "restored_version": version,
            "current_version": version,
            "prompt": restored_prompt,
        }

    def get_version_file_url(self, resource_type: str, resource_id: str, version: int) -> str | None:
        """
        獲取指定版本的檔案 URL

        Args:
            resource_type: 資源型別
            resource_id: 資源 ID
            version: 版本號

        Returns:
            檔案 URL，不存在時返回 None
        """
        info = self.get_versions(resource_type, resource_id)
        for v in info["versions"]:
            if v["version"] == version:
                return v.get("file_url")
        return None

    def get_version_prompt(self, resource_type: str, resource_id: str, version: int) -> str | None:
        """
        獲取指定版本的 prompt

        Args:
            resource_type: 資源型別
            resource_id: 資源 ID
            version: 版本號

        Returns:
            prompt 文字，不存在時返回 None
        """
        info = self.get_versions(resource_type, resource_id)
        for v in info["versions"]:
            if v["version"] == version:
                return v.get("prompt")
        return None

    def has_versions(self, resource_type: str, resource_id: str) -> bool:
        """
        檢查資源是否有版本記錄

        Args:
            resource_type: 資源型別
            resource_id: 資源 ID

        Returns:
            是否有版本記錄
        """
        return self.get_current_version(resource_type, resource_id) > 0
