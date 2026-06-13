"""資產檔案指紋計算 — 基於 mtime 的內容定址快取支援"""

from pathlib import Path

# 掃描的媒體子目錄
_MEDIA_SUBDIRS = ("storyboards", "videos", "thumbnails", "characters", "clues")

# 根目錄下的已知媒體檔案（如風格參考圖）
_ROOT_MEDIA_SUFFIXES = frozenset((".png", ".jpg", ".jpeg", ".webp", ".mp4"))


def _scan_subdir(prefix: str, dir_path: Path, fingerprints: dict[str, int]) -> None:
    """掃描單個媒體子目錄及其一級子目錄（跳過 versions/ 目錄）。"""
    for entry in dir_path.iterdir():
        if entry.is_file():
            fingerprints[f"{prefix}/{entry.name}"] = entry.stat().st_mtime_ns
        elif entry.is_dir() and entry.name != "versions":
            sub_prefix = f"{prefix}/{entry.name}"
            for sub_entry in entry.iterdir():
                if sub_entry.is_file():
                    fingerprints[f"{sub_prefix}/{sub_entry.name}"] = sub_entry.stat().st_mtime_ns


def compute_asset_fingerprints(project_path: Path) -> dict[str, int]:
    """
    掃描專案目錄下所有媒體檔案，返回 {相對路徑: mtime_ns_int} 對映。

    mtime_ns 為納秒級整數，用作 URL cache-bust 引數，精度高於秒級。
    對約 50 個檔案，耗時 <1ms（僅讀檔案系統後設資料）。
    """
    fingerprints: dict[str, int] = {}

    for subdir in _MEDIA_SUBDIRS:
        dir_path = project_path / subdir
        if dir_path.is_dir():
            _scan_subdir(subdir, dir_path, fingerprints)

    # 根目錄下的媒體檔案（如 style_reference.png）
    for f in project_path.iterdir():
        if f.is_file() and f.suffix.lower() in _ROOT_MEDIA_SUFFIXES:
            fingerprints[f.name] = f.stat().st_mtime_ns

    return fingerprints
