"""
檔案管理路由

處理檔案上傳和靜態資源服務
"""

import asyncio
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Body, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse

from lib import PROJECT_ROOT
from lib.docx_utils import read_docx_text
from lib.image_utils import normalize_uploaded_image
from lib.project_change_hints import emit_project_change_batch, project_change_source
from lib.project_manager import ProjectManager
from lib.source_text import read_text_with_fallback
from lib.step1_draft_sync import sync_draft_to_segments
from lib.version_manager import VersionManager
from server.auth import CurrentUser

router = APIRouter()

# 初始化專案管理器
pm = ProjectManager(PROJECT_ROOT / "projects")


def get_project_manager() -> ProjectManager:
    return pm


IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".webp"]
IMAGE_UPLOAD_TYPES = {
    "character",
    "character_ref",
    "clue",
    "clue_ref",
    "scene",
    "scene_ref",
    "storyboard",
    "storyboard_ref",
}
UPLOAD_DIRS = {
    "source": "source",
    "character": "characters",
    "character_ref": "characters/refs",
    "clue": "clues",
    "clue_ref": "clues/refs",
    "scene": "scenes",
    "scene_ref": "scenes/refs",
    "storyboard": "storyboards",
    "storyboard_ref": "storyboards/refs",
}
REF_UPLOAD_KINDS = {
    "character_ref": "character",
    "clue_ref": "clue",
    "scene_ref": "scene",
    "storyboard_ref": "storyboard",
}
METADATA_UPDATE_METHODS = {
    "character": "update_project_character_sheet",
    "character_ref": "update_character_reference_image",
    "clue": "update_clue_sheet",
    "clue_ref": "update_clue_reference_image",
    "scene": "update_scene_sheet",
    "scene_ref": "update_scene_reference_image",
    "storyboard_ref": "update_storyboard_reference_image",
}

# 允許的檔案型別
ALLOWED_EXTENSIONS = {
    "source": [".txt", ".md", ".doc", ".docx"],
    "character": IMAGE_EXTENSIONS,
    "character_ref": IMAGE_EXTENSIONS,
    "clue": IMAGE_EXTENSIONS,
    "clue_ref": IMAGE_EXTENSIONS,
    "scene": IMAGE_EXTENSIONS,
    "scene_ref": IMAGE_EXTENSIONS,
    "storyboard": IMAGE_EXTENSIONS,
    "storyboard_ref": IMAGE_EXTENSIONS,
}


def _build_upload_target(
    project_dir: Path, upload_type: str, original_filename: str, name: str | None
) -> tuple[Path, str]:
    upload_dir = UPLOAD_DIRS.get(upload_type, upload_type)
    target_dir = project_dir / upload_dir

    if upload_type == "source":
        return target_dir, original_filename

    stem = name or Path(original_filename).stem
    prefix = "scene_" if upload_type in ("storyboard", "storyboard_ref") and name else ""
    return target_dir, f"{prefix}{stem}.png"


def _update_upload_metadata(
    manager: ProjectManager,
    project_name: str,
    upload_type: str,
    name: str | None,
    relative_path: str,
    target_path: Path,
    filename: str,
) -> None:
    if not name:
        return

    update_method = METADATA_UPDATE_METHODS.get(upload_type)
    if update_method is None:
        return

    try:
        with project_change_source("webui"):
            getattr(manager, update_method)(project_name, name, relative_path)
        # 上傳參考圖 → 寫入 v0 可替換基底版本，並讓該資源 sheet 指向 v0
        if kind := REF_UPLOAD_KINDS.get(upload_type):
            _promote_reference_to_base_version(
                manager,
                project_name,
                kind=kind,
                name=name,
                ref_abs=target_path,
            )
    except KeyError:
        pass  # 對應實體不存在，忽略


# kind → (version resource_type, sheet 更新方法名)
_REF_KIND_MAP = {
    "character": ("characters", "update_project_character_sheet"),
    "clue": ("clues", "update_clue_sheet"),
    "scene": ("scenes", "update_scene_sheet"),
    "storyboard": ("storyboards", "update_storyboard_sheet"),
}

REFERENCE_IMAGE_CLEAR_FIELDS = {
    "characters": ("characters", ("character_sheet", "reference_image")),
    "clues": ("clues", ("clue_sheet", "reference_image")),
    "scenes": ("scenes", ("scene_sheet", "scene_ref")),
}
REFERENCE_IMAGE_RESOURCE_TYPES = set(REFERENCE_IMAGE_CLEAR_FIELDS) | {"storyboards"}


def _promote_reference_to_base_version(
    manager: ProjectManager,
    project_name: str,
    *,
    kind: str,
    name: str,
    ref_abs: Path,
) -> None:
    """把剛上傳的參考圖寫入 v0 基底版本，並讓資源 sheet 指向 v0 當前檔。

    v0 是可替換的基底（重複上傳會覆蓋同一槽位），上傳後即成為當前圖，
    可直接用於分鏡／影片生成（沿用既有讀 *_sheet 的流程）。
    """
    resource_type, sheet_setter = _REF_KIND_MAP[kind]
    project_path = manager.get_project_path(project_name)
    vm = VersionManager(project_path)
    result = vm.set_base_version(resource_type, name, ref_abs, prompt="使用者上傳")

    with project_change_source("webui"):
        getattr(manager, sheet_setter)(project_name, name, result["file"])


def _clear_reference_image_metadata(
    manager: ProjectManager,
    project_name: str,
    resource_type: str,
    resource_id: str,
) -> None:
    if resource_type == "storyboards":
        manager.update_storyboard_sheet(project_name, resource_id, "")
        manager.update_storyboard_reference_image(project_name, resource_id, "")
        return

    collection_name, fields = REFERENCE_IMAGE_CLEAR_FIELDS[resource_type]
    project = manager.load_project(project_name)
    resource = project.get(collection_name, {}).get(resource_id)
    if not resource:
        return

    for field in fields:
        resource[field] = ""
    manager.save_project(project_name, project)


@router.get("/files/{project_name}/{path:path}")
async def serve_project_file(project_name: str, path: str, request: Request):
    """服務專案內的靜態檔案（圖片/影片）"""
    try:

        def _sync():
            project_dir = get_project_manager().get_project_path(project_name)
            file_path = project_dir / path

            if not file_path.exists():
                raise HTTPException(status_code=404, detail=f"檔案不存在：{path}")

            # 安全檢查：確保路徑在專案目錄內
            try:
                file_path.resolve().relative_to(project_dir.resolve())
            except ValueError:
                raise HTTPException(status_code=403, detail="禁止存取專案目錄外的檔案")

            return file_path

        file_path = await asyncio.to_thread(_sync)

        # 內容定址快取：帶 ?v= 引數或 versions/ 路徑時設 immutable
        headers = {}
        if request.query_params.get("v") or path.startswith("versions/"):
            headers["Cache-Control"] = "public, max-age=31536000, immutable"

        return FileResponse(file_path, headers=headers)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"專案「{project_name}」不存在")


@router.post("/projects/{project_name}/upload/{upload_type}")
async def upload_file(
    project_name: str, upload_type: str, _user: CurrentUser, file: UploadFile = File(...), name: str = None
):
    """
    上傳檔案

    Args:
        project_name: 專案名稱
        upload_type: 上傳型別 (source/character/character_ref/clue/clue_ref/scene/scene_ref/storyboard)
        file: 上傳的檔案
        name: 可選，用於角色/線索/場景名稱，或分鏡 ID（自動更新後設資料）
    """
    if upload_type not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"無效的上傳型別：{upload_type}")

    # 檢查副檔名
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS[upload_type]:
        raise HTTPException(
            status_code=400,
            detail=f"不支援的檔案型別 {ext}，允許的型別：{ALLOWED_EXTENSIONS[upload_type]}",
        )

    try:
        content = await file.read()

        def _sync():
            manager = get_project_manager()
            project_dir = manager.get_project_path(project_name)
            target_dir, filename = _build_upload_target(project_dir, upload_type, file.filename, name)

            target_dir.mkdir(parents=True, exist_ok=True)

            # 儲存檔案（大於 2MB 時壓縮為 JPEG，否則校驗後原樣儲存）
            nonlocal content
            if upload_type in IMAGE_UPLOAD_TYPES:
                try:
                    content, ext = normalize_uploaded_image(content, Path(file.filename).suffix.lower())
                except ValueError:
                    raise HTTPException(status_code=400, detail="無效的圖片檔案，無法解析")
                filename = Path(filename).with_suffix(ext).name

            target_path = target_dir / filename
            with open(target_path, "wb") as f:
                f.write(content)

            relative_path = f"{UPLOAD_DIRS.get(upload_type, upload_type)}/{filename}"
            _update_upload_metadata(manager, project_name, upload_type, name, relative_path, target_path, filename)

            return {
                "success": True,
                "filename": filename,
                "path": relative_path,
                "url": f"/api/v1/files/{project_name}/{relative_path}",
            }

        return await asyncio.to_thread(_sync)

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"專案 '{project_name}' 不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_name}/files")
async def list_project_files(project_name: str, _user: CurrentUser):
    """列出專案中的所有檔案"""
    try:

        def _sync():
            project_dir = get_project_manager().get_project_path(project_name)

            files = {
                "source": [],
                "characters": [],
                "clues": [],
                "storyboards": [],
                "videos": [],
                "output": [],
            }

            for subdir, file_list in files.items():
                subdir_path = project_dir / subdir
                if subdir_path.exists():
                    for f in subdir_path.iterdir():
                        if f.is_file() and not f.name.startswith("."):
                            file_list.append(
                                {
                                    "name": f.name,
                                    "size": f.stat().st_size,
                                    "url": f"/api/v1/files/{project_name}/{subdir}/{f.name}",
                                }
                            )

            return {"files": files}

        return await asyncio.to_thread(_sync)

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"專案 '{project_name}' 不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_name}/source/{filename}")
async def get_source_file(project_name: str, filename: str, _user: CurrentUser):
    """獲取 source 檔案的文字內容"""
    try:

        def _sync():
            project_dir = get_project_manager().get_project_path(project_name)
            source_path = project_dir / "source" / filename

            if not source_path.exists():
                raise HTTPException(status_code=404, detail=f"檔案不存在: {filename}")

            # 安全檢查：確保路徑在專案目錄內
            try:
                source_path.resolve().relative_to(project_dir.resolve())
            except ValueError:
                raise HTTPException(status_code=403, detail="禁止訪問專案目錄外的檔案")

            if source_path.suffix.lower() == ".docx":
                return read_docx_text(source_path)
            return read_text_with_fallback(source_path)

        content = await asyncio.to_thread(_sync)
        return PlainTextResponse(content)

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"專案 '{project_name}' 不存在")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="檔案編碼錯誤，無法讀取")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/projects/{project_name}/source/{filename}")
async def update_source_file(
    project_name: str, filename: str, _user: CurrentUser, content: str = Body(..., media_type="text/plain")
):
    """更新或建立 source 檔案"""
    try:

        def _sync():
            project_dir = get_project_manager().get_project_path(project_name)
            source_dir = project_dir / "source"
            source_dir.mkdir(parents=True, exist_ok=True)
            source_path = source_dir / filename

            # 安全檢查：確保路徑在專案目錄內
            try:
                source_path.resolve().relative_to(project_dir.resolve())
            except ValueError:
                raise HTTPException(status_code=403, detail="禁止訪問專案目錄外的檔案")

            source_path.write_text(content, encoding="utf-8")
            return {"success": True, "path": f"source/{filename}"}

        return await asyncio.to_thread(_sync)

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"專案 '{project_name}' 不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/projects/{project_name}/source/{filename}")
async def delete_source_file(project_name: str, filename: str, _user: CurrentUser):
    """刪除 source 檔案"""
    try:

        def _sync():
            project_dir = get_project_manager().get_project_path(project_name)
            source_path = project_dir / "source" / filename

            # 安全檢查：確保路徑在專案目錄內
            try:
                source_path.resolve().relative_to(project_dir.resolve())
            except ValueError:
                raise HTTPException(status_code=403, detail="禁止訪問專案目錄外的檔案")

            if source_path.exists():
                source_path.unlink()
                return {"success": True}
            else:
                raise HTTPException(status_code=404, detail=f"檔案不存在: {filename}")

        return await asyncio.to_thread(_sync)

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"專案 '{project_name}' 不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 草稿檔案管理 ====================


@router.get("/projects/{project_name}/drafts")
async def list_drafts(project_name: str, _user: CurrentUser):
    """列出專案的所有草稿目錄和檔案"""
    try:

        def _sync():
            project_dir = get_project_manager().get_project_path(project_name)
            drafts_dir = project_dir / "drafts"

            result = {}
            if drafts_dir.exists():
                for episode_dir in sorted(drafts_dir.iterdir()):
                    if episode_dir.is_dir() and episode_dir.name.startswith("episode_"):
                        episode_num = episode_dir.name.replace("episode_", "")
                        files = []
                        for f in sorted(episode_dir.glob("*.md")):
                            files.append(
                                {
                                    "name": f.name,
                                    "step": _extract_step_number(f.name),
                                    "title": _get_step_title(f.name),
                                    "size": f.stat().st_size,
                                    "modified": f.stat().st_mtime,
                                }
                            )
                        result[episode_num] = files

            return {"drafts": result}

        return await asyncio.to_thread(_sync)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"專案 '{project_name}' 不存在")


def _extract_step_number(filename: str) -> int:
    """從檔名提取步驟編號"""
    import re

    match = re.search(r"step(\d+)", filename)
    return int(match.group(1)) if match else 0


def _get_step_files(content_mode: str) -> dict:
    """根據 content_mode 獲取步驟檔名對映"""
    if content_mode == "narration":
        return {1: "step1_segments.md"}
    else:
        return {1: "step1_normalized_script.md"}


def _get_step_title(filename: str) -> str:
    """獲取步驟標題"""
    titles = {
        "step1_normalized_script.md": "規範化劇本",
        "step1_segments.md": "片段拆分",
    }
    return titles.get(filename, filename)


def _get_content_mode(project_dir: Path) -> str:
    """從 project.json 讀取 content_mode"""
    project_json_path = project_dir / "project.json"
    if project_json_path.exists():
        with open(project_json_path, encoding="utf-8") as f:
            project_data = json.load(f)
            return project_data.get("content_mode", "drama")
    return "drama"


@router.get("/projects/{project_name}/drafts/{episode}/step{step_num}")
async def get_draft_content(project_name: str, episode: int, step_num: int, _user: CurrentUser):
    """獲取特定步驟的草稿內容"""
    try:

        def _sync():
            project_dir = get_project_manager().get_project_path(project_name)
            content_mode = _get_content_mode(project_dir)
            step_files = _get_step_files(content_mode)

            if step_num not in step_files:
                raise HTTPException(status_code=400, detail=f"無效的步驟編號: {step_num}")

            draft_path = project_dir / "drafts" / f"episode_{episode}" / step_files[step_num]

            # 草稿不存在是預期狀態（尚未生成），回空字串而非 404
            if not draft_path.exists():
                return ""

            return draft_path.read_text(encoding="utf-8")

        content = await asyncio.to_thread(_sync)
        return PlainTextResponse(content)

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"專案 '{project_name}' 不存在")


@router.put("/projects/{project_name}/drafts/{episode}/step{step_num}")
async def update_draft_content(
    project_name: str,
    episode: int,
    step_num: int,
    _user: CurrentUser,
    content: str = Body(..., media_type="text/plain"),
):
    """更新草稿內容"""
    try:

        def _sync():
            project_dir = get_project_manager().get_project_path(project_name)
            content_mode = _get_content_mode(project_dir)
            step_files = _get_step_files(content_mode)

            if step_num not in step_files:
                raise HTTPException(status_code=400, detail=f"無效的步驟編號: {step_num}")

            drafts_dir = project_dir / "drafts" / f"episode_{episode}"
            drafts_dir.mkdir(parents=True, exist_ok=True)

            draft_path = drafts_dir / step_files[step_num]
            is_new = not draft_path.exists()
            draft_path.write_text(content, encoding="utf-8")

            if step_num == 1:
                try:
                    sync_draft_to_segments(project_dir, episode, content, content_mode, get_project_manager())
                except Exception as e:
                    logger.error(f"Sync draft to segments failed in update_draft_content: {e}")

            # 發射 draft 事件通知前端
            action = "created" if is_new else "updated"
            label_prefix = "片段拆分" if content_mode == "narration" else "規範化劇本"
            change = {
                "entity_type": "draft",
                "action": action,
                "entity_id": f"episode_{episode}_step{step_num}",
                "label": f"第 {episode} 集{label_prefix}",
                "episode": episode,
                "focus": {
                    "pane": "episode",
                    "episode": episode,
                },
                "important": is_new,
            }
            try:
                emit_project_change_batch(project_name, [change], source="worker")
            except Exception:
                logger.warning("傳送 draft 事件失敗 project=%s episode=%s", project_name, episode, exc_info=True)

            return {"success": True, "path": str(draft_path.relative_to(project_dir))}

        return await asyncio.to_thread(_sync)

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"專案 '{project_name}' 不存在")


@router.delete("/projects/{project_name}/drafts/{episode}/step{step_num}")
async def delete_draft(project_name: str, episode: int, step_num: int, _user: CurrentUser):
    """刪除草稿檔案"""
    try:

        def _sync():
            project_dir = get_project_manager().get_project_path(project_name)
            content_mode = _get_content_mode(project_dir)
            step_files = _get_step_files(content_mode)

            if step_num not in step_files:
                raise HTTPException(status_code=400, detail=f"無效的步驟編號: {step_num}")

            draft_path = project_dir / "drafts" / f"episode_{episode}" / step_files[step_num]

            if draft_path.exists():
                draft_path.unlink()
                return {"success": True}
            else:
                raise HTTPException(status_code=404, detail="草稿檔案不存在")

        return await asyncio.to_thread(_sync)

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"專案 '{project_name}' 不存在")


# ==================== 風格參考圖管理 ====================


@router.post("/projects/{project_name}/style-image")
async def upload_style_image(project_name: str, _user: CurrentUser, file: UploadFile = File(...)):
    """
    上傳風格參考圖並分析風格

    1. 儲存圖片到 projects/{project_name}/style_reference.png
    2. 呼叫 Gemini API 分析風格
    3. 更新 project.json 的 style_image 和 style_description 欄位
    """
    # 檢查檔案型別
    ext = Path(file.filename).suffix.lower()
    if ext not in [".png", ".jpg", ".jpeg", ".webp"]:
        raise HTTPException(
            status_code=400,
            detail=f"不支援的檔案型別 {ext}，允許的型別：.png, .jpg, .jpeg, .webp",
        )

    try:
        content = await file.read()

        def _sync_prepare():
            project_dir = get_project_manager().get_project_path(project_name)
            try:
                content_norm, new_ext = normalize_uploaded_image(content, Path(file.filename).suffix.lower())
            except ValueError:
                raise HTTPException(status_code=400, detail="無效的圖片檔案，無法解析")
            style_filename = f"style_reference{new_ext}"

            output_path = project_dir / style_filename
            with open(output_path, "wb") as f:
                f.write(content_norm)

            return output_path, style_filename

        output_path, style_filename = await asyncio.to_thread(_sync_prepare)

        # 呼叫 TextGenerator 分析風格（自動追蹤用量）
        from lib.text_backends.base import ImageInput, TextGenerationRequest, TextTaskType
        from lib.text_backends.prompts import STYLE_ANALYSIS_PROMPT
        from lib.text_generator import TextGenerator

        generator = await TextGenerator.create(TextTaskType.STYLE_ANALYSIS, project_name)
        result = await generator.generate(
            TextGenerationRequest(prompt=STYLE_ANALYSIS_PROMPT, images=[ImageInput(path=output_path)]),
            project_name=project_name,
        )
        style_description = result.text

        def _sync_save():
            # 更新 project.json
            project_data = get_project_manager().load_project(project_name)
            project_data["style_image"] = style_filename
            project_data["style_description"] = style_description
            with project_change_source("webui"):
                get_project_manager().save_project(project_name, project_data)

        await asyncio.to_thread(_sync_save)

        return {
            "success": True,
            "style_image": style_filename,
            "style_description": style_description,
            "url": f"/api/v1/files/{project_name}/{style_filename}",
        }

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"專案「{project_name}」不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/projects/{project_name}/style-image")
async def delete_style_image(project_name: str, _user: CurrentUser):
    """
    刪除風格參考圖及相關欄位
    """
    try:

        def _sync():
            project_dir = get_project_manager().get_project_path(project_name)

            # 刪除圖片檔案（相容所有可能的字尾）
            for suffix in (".jpg", ".jpeg", ".png", ".webp"):
                image_path = project_dir / f"style_reference{suffix}"
                if image_path.exists():
                    image_path.unlink()

            # 清除 project.json 中的相關欄位
            project_data = get_project_manager().load_project(project_name)
            project_data.pop("style_image", None)
            project_data.pop("style_description", None)
            with project_change_source("webui"):
                get_project_manager().save_project(project_name, project_data)

            return {"success": True}

        return await asyncio.to_thread(_sync)

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"專案「{project_name}」不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/projects/{project_name}/style-description")
async def update_style_description(
    project_name: str, _user: CurrentUser, style_description: str = Body(..., embed=True)
):
    """
    更新風格描述（手動編輯）
    """
    try:

        def _sync():
            project_data = get_project_manager().load_project(project_name)
            project_data["style_description"] = style_description
            with project_change_source("webui"):
                get_project_manager().save_project(project_name, project_data)

            return {"success": True, "style_description": style_description}

        return await asyncio.to_thread(_sync)

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"專案「{project_name}」不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/projects/{project_name}/style")
async def update_style(project_name: str, _user: CurrentUser, style: str = Body(..., embed=True)):
    """
    更新專案風格標籤
    """
    if style not in {"Photographic", "Anime", "3D Animation"}:
        raise HTTPException(status_code=400, detail="不支援的專案風格")

    try:

        def _sync():
            project_data = get_project_manager().load_project(project_name)
            project_data["style"] = style
            with project_change_source("webui"):
                get_project_manager().save_project(project_name, project_data)

            return {"success": True, "style": style}

        return await asyncio.to_thread(_sync)

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"專案「{project_name}」不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/projects/{project_name}/reference-image/{resource_type}/{resource_id}")
async def delete_reference_image(
    project_name: str,
    resource_type: str,
    resource_id: str,
    _user: CurrentUser,
):
    """
    清除特定資源的參考圖與 v0 基底版本
    """
    if resource_type not in REFERENCE_IMAGE_RESOURCE_TYPES:
        raise HTTPException(status_code=400, detail=f"不支援的資源型別：{resource_type}")

    try:

        def _sync():
            manager = get_project_manager()
            project_path = manager.get_project_path(project_name)

            vm = VersionManager(project_path)
            vm.remove_base_version(resource_type, resource_id)

            with project_change_source("webui"):
                _clear_reference_image_metadata(manager, project_name, resource_type, resource_id)

            return {"success": True}

        return await asyncio.to_thread(_sync)

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"專案 '{project_name}' 不存在")
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("清除參考圖失敗")
        raise HTTPException(status_code=500, detail=str(e))
