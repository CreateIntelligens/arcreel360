"""
版本管理 API 路由

處理版本查詢和還原請求。
"""

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

from lib import PROJECT_ROOT
from lib.project_change_hints import project_change_source
from lib.project_manager import ProjectManager
from lib.version_manager import VersionManager
from server.auth import CurrentUser

router = APIRouter()

# 初始化專案管理器
pm = ProjectManager(PROJECT_ROOT / "projects")

_RESOURCE_FILE_PATTERNS: dict[str, tuple[str, str]] = {
    "storyboards": ("storyboards", "scene_{id}.png"),
    "videos": ("videos", "scene_{id}.mp4"),
    "characters": ("characters", "{id}.png"),
    "clues": ("clues", "{id}.png"),
    "output": ("output", "episode_{id}_final.mp4"),
}


def get_project_manager() -> ProjectManager:
    return pm


def get_version_manager(project_name: str) -> VersionManager:
    """獲取專案的版本管理器"""
    project_path = get_project_manager().get_project_path(project_name)
    return VersionManager(project_path)


def _resolve_resource_path(
    resource_type: str,
    resource_id: str,
    project_path: Path,
) -> tuple[Path, str]:
    """返回 (current_file_absolute, relative_file_path)，資源型別無效時丟擲 HTTPException。"""
    pattern = _RESOURCE_FILE_PATTERNS.get(resource_type)
    if pattern is None:
        raise HTTPException(status_code=400, detail=f"不支援的資源型別: {resource_type}")
    subdir, name_tpl = pattern
    name = name_tpl.format(id=resource_id)
    return project_path / subdir / name, f"{subdir}/{name}"


def _sync_storyboard_metadata(
    project_name: str,
    resource_id: str,
    file_path: str,
    project_path: Path,
) -> None:
    scripts_dir = project_path / "scripts"
    if not scripts_dir.exists():
        return
    for script_file in scripts_dir.glob("*.json"):
        try:
            with project_change_source("webui"):
                get_project_manager().update_scene_asset(
                    project_name=project_name,
                    script_filename=script_file.name,
                    scene_id=resource_id,
                    asset_type="storyboard_image",
                    asset_path=file_path,
                )
        except KeyError:
            continue
        except Exception as exc:
            logger.warning("同步分鏡後設資料失敗: %s", exc)
            continue


def _sync_metadata(
    resource_type: str,
    project_name: str,
    resource_id: str,
    file_path: str,
    project_path: Path,
) -> None:
    """還原後同步後設資料，確保引用指向統一檔案路徑。"""
    if resource_type == "characters":
        try:
            with project_change_source("webui"):
                get_project_manager().update_project_character_sheet(project_name, resource_id, file_path)
        except KeyError:
            pass  # 角色條目可能已從 project.json 刪除，跳過後設資料同步
    elif resource_type == "clues":
        try:
            with project_change_source("webui"):
                get_project_manager().update_clue_sheet(project_name, resource_id, file_path)
        except KeyError:
            pass  # 線索條目可能已從 project.json 刪除，跳過後設資料同步
    elif resource_type == "storyboards":
        _sync_storyboard_metadata(project_name, resource_id, file_path, project_path)


# ==================== 版本查詢 ====================


@router.get("/projects/{project_name}/versions/{resource_type}/{resource_id}")
async def get_versions(
    project_name: str,
    resource_type: str,
    resource_id: str,
    _user: CurrentUser,
):
    """
    獲取資源的所有版本列表

    Args:
        project_name: 專案名稱
        resource_type: 資源型別 (storyboards, videos, characters, clues)
        resource_id: 資源 ID
    """
    try:

        def _sync():
            vm = get_version_manager(project_name)
            versions_info = vm.get_versions(resource_type, resource_id)
            return {"resource_type": resource_type, "resource_id": resource_id, **versions_info}

        return await asyncio.to_thread(_sync)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 版本還原 ====================


@router.post("/projects/{project_name}/versions/{resource_type}/{resource_id}/restore/{version}")
async def restore_version(
    project_name: str,
    resource_type: str,
    resource_id: str,
    version: int,
    _user: CurrentUser,
):
    """
    切換到指定版本

    會將指定版本複製到當前路徑，並把當前版本指標切換到該版本。

    Args:
        project_name: 專案名稱
        resource_type: 資源型別
        resource_id: 資源 ID
        version: 要還原的版本號
    """
    try:

        def _sync():
            vm = get_version_manager(project_name)
            project_path = get_project_manager().get_project_path(project_name)
            current_file, file_path = _resolve_resource_path(resource_type, resource_id, project_path)

            result = vm.restore_version(
                resource_type=resource_type,
                resource_id=resource_id,
                version=version,
                current_file=current_file,
            )

            _sync_metadata(resource_type, project_name, resource_id, file_path, project_path)

            # 計算還原後檔案的 fingerprint；影片還原時同步刪除縮圖（內容已失效）
            asset_fingerprints: dict[str, int] = {}
            if current_file.exists():
                asset_fingerprints[file_path] = current_file.stat().st_mtime_ns

            if resource_type == "videos":
                thumbnail_path = project_path / "thumbnails" / f"scene_{resource_id}.jpg"
                thumbnail_key = f"thumbnails/scene_{resource_id}.jpg"
                thumbnail_path.unlink(missing_ok=True)
                # fingerprint=0 通知前端該檔案已失效（poster 消失直到生成）
                asset_fingerprints[thumbnail_key] = 0

            return {
                "success": True,
                **result,
                "file_path": file_path,
                "asset_fingerprints": asset_fingerprints,
            }

        return await asyncio.to_thread(_sync)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))
