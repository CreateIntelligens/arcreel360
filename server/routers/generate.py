"""
生成 API 路由

處理分鏡圖、影片、角色圖、線索圖的生成請求。
所有生成請求入隊到 GenerationQueue，由 GenerationWorker 非同步執行。
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from lib import PROJECT_ROOT
from lib.episode_overrides import read_episode_override as _read_episode_override
from lib.generation_queue import get_generation_queue
from lib.project_manager import ProjectManager
from lib.prompt_language import helper_prompt_language_clause
from lib.prompt_utils import (
    is_structured_image_prompt,
    is_structured_video_prompt,
)
from lib.storyboard_sequence import (
    find_storyboard_item,
    get_storyboard_items,
)
from server.auth import CurrentUser

router = APIRouter()

# 初始化管理器
pm = ProjectManager(PROJECT_ROOT / "projects")


def get_project_manager() -> ProjectManager:
    return pm


# ==================== 請求模型 ====================


class GenerateStoryboardRequest(BaseModel):
    prompt: str | dict
    script_file: str


class GenerateVideoRequest(BaseModel):
    prompt: str | dict
    script_file: str
    duration_seconds: int | None = None  # 改為 None，由服務層解析
    seed: int | None = None


class GenerateCharacterRequest(BaseModel):
    prompt: str


class GenerateClueRequest(BaseModel):
    prompt: str


class GenerateSceneRequest(BaseModel):
    prompt: str


_LEGACY_PROVIDER_NAMES: dict[str, str] = {
    "gemini": "gemini-aistudio",
    "aistudio": "gemini-aistudio",
    "vertex": "gemini-vertex",
}


def _normalize_provider_id(raw: str) -> str:
    """將舊格式 provider 名稱歸一化為標準 provider_id。"""
    return _LEGACY_PROVIDER_NAMES.get(raw, raw)


def _read_scene_backend_override(
    project_name: str,
    script_file: str | None,
    resource_id: str | None,
    field: str,
) -> str | None:
    """讀取 scene-level backend 覆蓋（"provider/model" 字串）。

    field: "image_backend" or "video_backend"
    回傳 None 表示該 scene 未設定覆蓋（沿用上層）。
    """
    if not script_file or not resource_id:
        return None
    try:
        script = get_project_manager().load_script(project_name, script_file)
    except FileNotFoundError:
        return None

    items, id_field, _, _, _ = get_storyboard_items(script)
    resolved = find_storyboard_item(items, id_field, resource_id)
    if resolved is None:
        return None
    item, _ = resolved
    value = item.get(field)
    return value if isinstance(value, str) and value.strip() else None


def _split_backend_str(raw: str) -> tuple[str, str]:
    """將 "provider/model" 解析為 (provider_id, model_id)。"""
    if "/" in raw:
        provider, model = raw.split("/", 1)
        return provider, model
    return _normalize_provider_id(raw), ""


def _snapshot_scene_backend(
    project_name: str,
    *,
    script_file: str | None,
    resource_id: str | None,
    field: str,
) -> tuple[str, str] | None:
    scene_override = _read_scene_backend_override(project_name, script_file, resource_id, field)
    return _split_backend_str(scene_override) if scene_override else None


def _snapshot_image_backend(
    project_name: str,
    *,
    script_file: str | None = None,
    resource_id: str | None = None,
    project: dict | None = None,
    character_name: str | None = None,
    clue_name: str | None = None,
    scene_name: str | None = None,
) -> dict:
    """快照圖片供應商配置，返回可合併到 payload 的字典。

    優先順序：entity-level image_backend > scene-level image_backend > episode-level image_backend > 專案級 image_backend > 系統級預設。
    傳入 script_file + resource_id 啟用 scene-level 覆蓋查詢。
    """
    if project is None:
        project = get_project_manager().load_project(project_name)

    # 1. 實體級（角色、道具、專案場景）的覆蓋
    entity_backend = None
    if character_name:
        entity_backend = project.get("characters", {}).get(character_name, {}).get("image_backend")
    elif clue_name:
        entity_backend = project.get("clues", {}).get(clue_name, {}).get("image_backend")
    elif scene_name:
        entity_backend = project.get("scenes", {}).get(scene_name, {}).get("image_backend")

    if entity_backend:
        provider, model = _split_backend_str(entity_backend)
        return {"image_provider": provider, "image_model": model}

    # 2. 場景與分集覆蓋
    scene_backend = _snapshot_scene_backend(
        project_name,
        script_file=script_file,
        resource_id=resource_id,
        field="image_backend",
    )
    # scene-level 與 episode-level 圖片尺寸覆蓋（image_size）
    scene_image_size = _read_scene_backend_override(project_name, script_file, resource_id, "image_size")
    episode_image_size = _read_episode_override(project, script_file, "image_size")
    img_size = scene_image_size or episode_image_size
    size_patch = {"image_size": img_size} if img_size else {}

    if scene_backend:
        provider, model = scene_backend
        return {"image_provider": provider, "image_model": model, **size_patch}

    episode_image_backend = _read_episode_override(project, script_file, "image_backend")
    if episode_image_backend:
        provider, model = _split_backend_str(episode_image_backend)
        return {"image_provider": provider, "image_model": model, **size_patch}

    project_image_backend = project.get("image_backend")  # 格式: "provider_id/model"
    if not project_image_backend:
        return size_patch  # 無專案級覆蓋，使用全域性預設

    image_provider, image_model = _split_backend_str(project_image_backend)
    return {
        "image_provider": image_provider,
        "image_model": image_model,
        **size_patch,
    }


def _snapshot_video_backend(
    project_name: str,
    *,
    script_file: str | None = None,
    resource_id: str | None = None,
) -> dict:
    """快照影片供應商配置，返回可合併到 payload 的字典。

    優先順序：scene-level video_backend > episode-level video_backend > 專案級 video_backend > 系統級預設。
    """
    project = get_project_manager().load_project(project_name)

    scene_backend = _snapshot_scene_backend(
        project_name,
        script_file=script_file,
        resource_id=resource_id,
        field="video_backend",
    )
    # scene-level 與 episode-level 解析度覆蓋（video_resolution）
    scene_resolution = _read_scene_backend_override(project_name, script_file, resource_id, "video_resolution")
    episode_resolution = _read_episode_override(project, script_file, "video_resolution")
    res = scene_resolution or episode_resolution
    res_patch = {"video_resolution": res} if res else {}

    if scene_backend:
        provider, model = scene_backend
        return {
            "video_provider": provider,
            "video_provider_settings": {"model": model} if model else {},
            **res_patch,
        }

    episode_video_backend = _read_episode_override(project, script_file, "video_backend")
    if episode_video_backend:
        provider, model = _split_backend_str(episode_video_backend)
        return {
            "video_provider": provider,
            "video_provider_settings": {"model": model} if model else {},
            **res_patch,
        }

    # 專案級由 _resolve_video_backend 處理，這裡不提前快照（保持原行為）
    return res_patch


# ==================== 分鏡圖生成 ====================


@router.post("/projects/{project_name}/generate/storyboard/{segment_id}")
async def generate_storyboard(
    project_name: str,
    segment_id: str,
    req: GenerateStoryboardRequest,
    _user: CurrentUser,
):
    """
    提交分鏡圖生成任務到佇列，立即返回 task_id。

    生成由 GenerationWorker 非同步執行，狀態透過 SSE 推送。
    """
    try:

        def _sync():
            manager = get_project_manager()
            manager.load_project(project_name)
            script = manager.load_script(project_name, req.script_file)
            items, id_field, _, _, _ = get_storyboard_items(script)
            resolved = find_storyboard_item(items, id_field, segment_id)
            if resolved is None:
                raise HTTPException(status_code=404, detail=f"片段/場景 '{segment_id}' 不存在")
            return _snapshot_image_backend(
                project_name,
                script_file=req.script_file,
                resource_id=segment_id,
            )

        image_snapshot = await asyncio.to_thread(_sync)

        # 驗證 prompt 格式
        if isinstance(req.prompt, dict):
            if not is_structured_image_prompt(req.prompt):
                raise HTTPException(
                    status_code=400,
                    detail="prompt 必須是字串或包含 scene/composition 的物件",
                )
            scene_text = str(req.prompt.get("scene", "")).strip()
            if not scene_text:
                raise HTTPException(status_code=400, detail="prompt.scene 不能為空")
        elif not isinstance(req.prompt, str):
            raise HTTPException(status_code=400, detail="prompt 必須是字串或物件")

        # 入隊
        queue = get_generation_queue()
        result = await queue.enqueue_task(
            project_name=project_name,
            task_type="storyboard",
            media_type="image",
            resource_id=segment_id,
            script_file=req.script_file,
            payload={
                "prompt": req.prompt,
                "script_file": req.script_file,
                **image_snapshot,
            },
            source="webui",
            user_id=_user.id,
        )

        return {
            "success": True,
            "task_id": result["task_id"],
            "message": f"分鏡「{segment_id}」生成任務已提交",
        }

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 影片生成 ====================


@router.post("/projects/{project_name}/generate/video/{segment_id}")
async def generate_video(project_name: str, segment_id: str, req: GenerateVideoRequest, _user: CurrentUser):
    """
    提交影片生成任務到佇列，立即返回 task_id。

    需要先有分鏡圖作為起始幀。生成由 GenerationWorker 非同步執行。
    """
    try:

        def _sync():
            manager = get_project_manager()
            project = manager.load_project(project_name)
            project_path = manager.get_project_path(project_name)
            storyboard_file = project_path / "storyboards" / f"scene_{segment_id}.png"
            if not storyboard_file.exists():
                raise HTTPException(status_code=400, detail=f"請先生成分鏡圖 scene_{segment_id}.png")

            script = manager.load_script(project_name, req.script_file)
            items, id_field, _, _, _ = get_storyboard_items(script)
            resolved = find_storyboard_item(items, id_field, segment_id)

            duration = req.duration_seconds
            if duration is None and resolved:
                item, _ = resolved
                duration = item.get("duration_seconds")
            if duration is None:
                duration = _read_episode_override(project, req.script_file, "duration_seconds")

            snapshot = _snapshot_video_backend(
                project_name,
                script_file=req.script_file,
                resource_id=segment_id,
            )
            return snapshot, duration

        video_snapshot, duration = await asyncio.to_thread(_sync)

        # 驗證 prompt 格式
        if isinstance(req.prompt, dict):
            if not is_structured_video_prompt(req.prompt):
                raise HTTPException(
                    status_code=400,
                    detail="prompt 必須是字串或包含 action/camera_motion 的物件",
                )
            action_text = str(req.prompt.get("action", "")).strip()
            if not action_text:
                raise HTTPException(status_code=400, detail="prompt.action 不能為空")
            dialogue = req.prompt.get("dialogue", [])
            if dialogue is not None and not isinstance(dialogue, list):
                raise HTTPException(status_code=400, detail="prompt.dialogue 必須是陣列")
        elif not isinstance(req.prompt, str):
            raise HTTPException(status_code=400, detail="prompt 必須是字串或物件")

        # 入隊（provider 由服務層根據配置自動解析，scene 覆蓋透過 video_snapshot 注入）
        queue = get_generation_queue()
        result = await queue.enqueue_task(
            project_name=project_name,
            task_type="video",
            media_type="video",
            resource_id=segment_id,
            script_file=req.script_file,
            payload={
                "prompt": req.prompt,
                "script_file": req.script_file,
                "duration_seconds": duration,
                **video_snapshot,
                "seed": req.seed,
            },
            source="webui",
            user_id=_user.id,
        )

        return {
            "success": True,
            "task_id": result["task_id"],
            "message": f"影片「{segment_id}」生成任務已提交",
        }

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 角色設計圖生成 ====================


@router.post("/projects/{project_name}/generate/character/{char_name}")
async def generate_character(
    project_name: str,
    char_name: str,
    req: GenerateCharacterRequest,
    _user: CurrentUser,
):
    """
    提交角色設計圖生成任務到佇列，立即回傳 task_id。
    """
    try:

        def _sync():
            project = get_project_manager().load_project(project_name)
            if char_name not in project.get("characters", {}):
                raise HTTPException(status_code=404, detail=f"角色「{char_name}」不存在")
            return _snapshot_image_backend(project_name, character_name=char_name, project=project)

        image_snapshot = await asyncio.to_thread(_sync)

        # 入隊
        queue = get_generation_queue()
        result = await queue.enqueue_task(
            project_name=project_name,
            task_type="character",
            media_type="image",
            resource_id=char_name,
            payload={
                "prompt": req.prompt,
                **image_snapshot,
            },
            source="webui",
            user_id=_user.id,
        )

        return {
            "success": True,
            "task_id": result["task_id"],
            "message": f"角色「{char_name}」設計圖生成任務已提交",
        }

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 批次生成請求模型 ====================


class BatchStoryboardRequest(BaseModel):
    script_file: str
    ids: list[str] | None = None
    force: bool = False


class BatchVideoRequest(BaseModel):
    script_file: str
    ids: list[str] | None = None
    force: bool = False


class BatchCharacterRequest(BaseModel):
    names: list[str] | None = None
    force: bool = False


class BatchClueRequest(BaseModel):
    names: list[str] | None = None
    force: bool = False


class BatchSceneRequest(BaseModel):
    names: list[str] | None = None
    force: bool = False


# ==================== 批次：分鏡圖 ====================


@router.post("/projects/{project_name}/generate/storyboards/batch")
async def generate_storyboards_batch(
    project_name: str,
    req: BatchStoryboardRequest,
    _user: CurrentUser,
):
    """批次提交分鏡圖生成任務。

    - `ids=null` 時取整集所有 segment/scene
    - `force=false` 時跳過已存在 storyboards/scene_{id}.png 的項目
    """
    try:

        def _sync():
            manager = get_project_manager()
            manager.load_project(project_name)
            script = manager.load_script(project_name, req.script_file)
            items, id_field, _, _, _ = get_storyboard_items(script)
            project_path = manager.get_project_path(project_name)

            requested_ids: list[str]
            if req.ids is None:
                requested_ids = [str(item.get(id_field)) for item in items if item.get(id_field)]
            else:
                requested_ids = [str(i) for i in req.ids]

            valid_ids: set[str] = {str(item.get(id_field)) for item in items if item.get(id_field)}

            to_enqueue: list[str] = []
            skipped: list[dict] = []
            for sid in requested_ids:
                if sid not in valid_ids:
                    skipped.append({"id": sid, "reason": "not_found"})
                    continue
                if not req.force and (project_path / "storyboards" / f"scene_{sid}.png").exists():
                    skipped.append({"id": sid, "reason": "already_exists"})
                    continue
                to_enqueue.append(sid)
            # 每個 scene 各自 snapshot（支援 scene-level 覆蓋）
            snapshots: dict[str, dict] = {
                sid: _snapshot_image_backend(project_name, script_file=req.script_file, resource_id=sid)
                for sid in to_enqueue
            }
            return to_enqueue, skipped, snapshots

        to_enqueue, skipped, snapshots = await asyncio.to_thread(_sync)

        queue = get_generation_queue()
        enqueued: list[str] = []
        for sid in to_enqueue:
            await queue.enqueue_task(
                project_name=project_name,
                task_type="storyboard",
                media_type="image",
                resource_id=sid,
                script_file=req.script_file,
                payload={
                    "prompt": "",  # worker 會從劇本讀取 prompt
                    "script_file": req.script_file,
                    "from_batch": True,
                    **snapshots.get(sid, {}),
                },
                source="webui",
                user_id=_user.id,
            )
            enqueued.append(sid)

        return {"enqueued": enqueued, "skipped": skipped}

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 批次：影片 ====================


@router.post("/projects/{project_name}/generate/videos/batch")
async def generate_videos_batch(
    project_name: str,
    req: BatchVideoRequest,
    _user: CurrentUser,
):
    """批次提交影片生成任務。force=false 時跳過已存在 videos/scene_{id}.mp4。"""
    try:

        def _sync():
            manager = get_project_manager()
            manager.load_project(project_name)
            script = manager.load_script(project_name, req.script_file)
            items, id_field, _, _, _ = get_storyboard_items(script)
            project_path = manager.get_project_path(project_name)

            requested_ids: list[str]
            if req.ids is None:
                requested_ids = [str(item.get(id_field)) for item in items if item.get(id_field)]
            else:
                requested_ids = [str(i) for i in req.ids]

            valid_ids: set[str] = {str(item.get(id_field)) for item in items if item.get(id_field)}

            to_enqueue: list[str] = []
            skipped: list[dict] = []
            for sid in requested_ids:
                if sid not in valid_ids:
                    skipped.append({"id": sid, "reason": "not_found"})
                    continue
                if not (project_path / "storyboards" / f"scene_{sid}.png").exists():
                    skipped.append({"id": sid, "reason": "missing_storyboard"})
                    continue
                if not req.force and (project_path / "videos" / f"scene_{sid}.mp4").exists():
                    skipped.append({"id": sid, "reason": "already_exists"})
                    continue
                to_enqueue.append(sid)
            # 每個 scene 各自 snapshot（支援 scene-level 影片後端覆蓋）
            snapshots: dict[str, dict] = {
                sid: _snapshot_video_backend(project_name, script_file=req.script_file, resource_id=sid)
                for sid in to_enqueue
            }
            return to_enqueue, skipped, snapshots

        to_enqueue, skipped, snapshots = await asyncio.to_thread(_sync)

        queue = get_generation_queue()
        enqueued: list[str] = []
        for sid in to_enqueue:
            await queue.enqueue_task(
                project_name=project_name,
                task_type="video",
                media_type="video",
                resource_id=sid,
                script_file=req.script_file,
                payload={
                    "prompt": "",
                    "script_file": req.script_file,
                    "from_batch": True,
                    **snapshots.get(sid, {}),
                },
                source="webui",
                user_id=_user.id,
            )
            enqueued.append(sid)

        return {"enqueued": enqueued, "skipped": skipped}

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 批次：角色 ====================


@router.post("/projects/{project_name}/generate/characters/batch")
async def generate_characters_batch(
    project_name: str,
    req: BatchCharacterRequest,
    _user: CurrentUser,
):
    """批次提交角色設計圖生成任務。force=false 時跳過已有 character_sheet 的角色。"""
    try:

        def _sync():
            project = get_project_manager().load_project(project_name)
            characters: dict = project.get("characters", {})

            requested = [str(n) for n in (req.names if req.names is not None else list(characters.keys()))]

            to_enqueue: list[str] = []
            skipped: list[dict] = []
            for name in requested:
                if name not in characters:
                    skipped.append({"id": name, "reason": "not_found"})
                    continue
                if not req.force and characters[name].get("character_sheet"):
                    skipped.append({"id": name, "reason": "already_exists"})
                    continue
                to_enqueue.append(name)
            return to_enqueue, skipped, project, characters

        to_enqueue, skipped, project, characters = await asyncio.to_thread(_sync)

        queue = get_generation_queue()
        enqueued: list[str] = []
        for name in to_enqueue:
            prompt = characters[name].get("description", "")
            char_snapshot = _snapshot_image_backend(project_name, character_name=name, project=project)
            await queue.enqueue_task(
                project_name=project_name,
                task_type="character",
                media_type="image",
                resource_id=name,
                payload={
                    "prompt": prompt,
                    "from_batch": True,
                    **char_snapshot,
                },
                source="webui",
                user_id=_user.id,
            )
            enqueued.append(name)

        return {"enqueued": enqueued, "skipped": skipped}

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 批次：線索 ====================


@router.post("/projects/{project_name}/generate/clues/batch")
async def generate_clues_batch(
    project_name: str,
    req: BatchClueRequest,
    _user: CurrentUser,
):
    """批次提交線索設計圖生成任務。force=false 時跳過已有 clue_sheet 的線索。"""
    try:

        def _sync():
            project = get_project_manager().load_project(project_name)
            clues: dict = project.get("clues", {})

            requested = [str(n) for n in (req.names if req.names is not None else list(clues.keys()))]

            to_enqueue: list[str] = []
            skipped: list[dict] = []
            for name in requested:
                if name not in clues:
                    skipped.append({"id": name, "reason": "not_found"})
                    continue
                if not req.force and clues[name].get("clue_sheet"):
                    skipped.append({"id": name, "reason": "already_exists"})
                    continue
                to_enqueue.append(name)
            return to_enqueue, skipped, project, clues

        to_enqueue, skipped, project, clues = await asyncio.to_thread(_sync)

        queue = get_generation_queue()
        enqueued: list[str] = []
        for name in to_enqueue:
            prompt = clues[name].get("description", "")
            clue_snapshot = _snapshot_image_backend(project_name, clue_name=name, project=project)
            await queue.enqueue_task(
                project_name=project_name,
                task_type="clue",
                media_type="image",
                resource_id=name,
                payload={
                    "prompt": prompt,
                    "from_batch": True,
                    **clue_snapshot,
                },
                source="webui",
                user_id=_user.id,
            )
            enqueued.append(name)

        return {"enqueued": enqueued, "skipped": skipped}

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 批次：場景 ====================


@router.post("/projects/{project_name}/generate/scenes/batch")
async def generate_scenes_batch(
    project_name: str,
    req: BatchSceneRequest,
    _user: CurrentUser,
):
    """批次提交場景設計圖生成任務。force=false 時跳過已有 scene_sheet 的場景。"""
    try:

        def _sync():
            project = get_project_manager().load_project(project_name)
            scenes: dict = project.get("scenes", {})

            requested = [str(n) for n in (req.names if req.names is not None else list(scenes.keys()))]

            to_enqueue: list[str] = []
            skipped: list[dict] = []
            for name in requested:
                if name not in scenes:
                    skipped.append({"id": name, "reason": "not_found"})
                    continue
                if not req.force and scenes[name].get("scene_sheet"):
                    skipped.append({"id": name, "reason": "already_exists"})
                    continue
                to_enqueue.append(name)
            return to_enqueue, skipped, project, scenes

        to_enqueue, skipped, project, scenes = await asyncio.to_thread(_sync)

        queue = get_generation_queue()
        enqueued: list[str] = []
        for name in to_enqueue:
            prompt = scenes[name].get("description", "")
            scene_snapshot = _snapshot_image_backend(project_name, scene_name=name, project=project)
            await queue.enqueue_task(
                project_name=project_name,
                task_type="scene",
                media_type="image",
                resource_id=name,
                payload={
                    "prompt": prompt,
                    "from_batch": True,
                    **scene_snapshot,
                },
                source="webui",
                user_id=_user.id,
            )
            enqueued.append(name)

        return {"enqueued": enqueued, "skipped": skipped}

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 線索設計圖生成 ====================


@router.post("/projects/{project_name}/generate/clue/{clue_name}")
async def generate_clue(project_name: str, clue_name: str, req: GenerateClueRequest, _user: CurrentUser):
    """
    提交道具設計圖生成任務到佇列，立即回傳 task_id。
    """
    try:

        def _sync():
            project = get_project_manager().load_project(project_name)
            if clue_name not in project.get("clues", {}):
                raise HTTPException(status_code=404, detail=f"道具「{clue_name}」不存在")
            return _snapshot_image_backend(project_name, clue_name=clue_name, project=project)

        image_snapshot = await asyncio.to_thread(_sync)

        # 入隊
        queue = get_generation_queue()
        result = await queue.enqueue_task(
            project_name=project_name,
            task_type="clue",
            media_type="image",
            resource_id=clue_name,
            payload={
                "prompt": req.prompt,
                **image_snapshot,
            },
            source="webui",
            user_id=_user.id,
        )

        return {
            "success": True,
            "task_id": result["task_id"],
            "message": f"道具「{clue_name}」設計圖生成任務已提交",
        }

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 場景設計圖生成 ====================


@router.post("/projects/{project_name}/generate/scene/{scene_name}")
async def generate_scene(project_name: str, scene_name: str, req: GenerateSceneRequest, _user: CurrentUser):
    """
    提交場景設計圖生成任務到佇列，立即回傳 task_id。
    """
    try:

        def _sync():
            project = get_project_manager().load_project(project_name)
            if scene_name not in project.get("scenes", {}):
                raise HTTPException(status_code=404, detail=f"場景「{scene_name}」不存在")
            return _snapshot_image_backend(project_name, scene_name=scene_name, project=project)

        image_snapshot = await asyncio.to_thread(_sync)

        queue = get_generation_queue()
        result = await queue.enqueue_task(
            project_name=project_name,
            task_type="scene",
            media_type="image",
            resource_id=scene_name,
            payload={
                "prompt": req.prompt,
                **image_snapshot,
            },
            source="webui",
            user_id=_user.id,
        )

        return {
            "success": True,
            "task_id": result["task_id"],
            "message": f"場景「{scene_name}」設計圖生成任務已提交",
        }

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))


class OptimizePromptRequest(BaseModel):
    type: str  # "character" | "clue" | "scene" | "image_prompt" | "video_prompt"
    name: str | None = None
    description: str
    instruction: str | None = None
    model: str | None = None


_HELPER_PROMPT_MIN_CHARS = 30
_HELPER_PROMPT_DANGLING_SUFFIXES = ("，", "、", "：", ":", "；", ";", "（", "(")
_HELPER_LOREBOOK_MAX_ENTRIES = 30
_HELPER_LOREBOOK_DESC_MAX_CHARS = 220
_HELPER_SOURCE_PRIORITY_RULE = (
    "請優先依據「基本描述/分鏡旁白內容」中的最新原文或目前片段內容；設定集只用於補足角色、道具、場景與風格一致性。"
)
_HELPER_TYPE_LABELS = {
    "character": "角色",
    "clue": "道具/線索",
    "scene": "場景",
    "image_prompt": "分鏡圖提示詞",
    "video_prompt": "影片動作提示詞",
}
_HELPER_LOREBOOK_SECTIONS: tuple[tuple[str, str, tuple[tuple[str, str], ...]], ...] = (
    (
        "角色設定集",
        "characters",
        (("voice_style", "聲線/語氣"), ("reference_image", "參考圖"), ("character_sheet", "角色圖")),
    ),
    (
        "道具/線索設定集",
        "clues",
        (("importance", "重要程度"), ("reference_image", "參考圖"), ("clue_sheet", "道具圖")),
    ),
    ("場景設定集", "scenes", (("scene_ref", "參考圖"), ("scene_sheet", "場景圖"))),
)


def _clean_helper_prompt(text: str) -> str:
    prompt_output = text.strip()
    for quote in ('"', "'"):
        if prompt_output.startswith(quote) and prompt_output.endswith(quote):
            prompt_output = prompt_output[1:-1].strip()
    return prompt_output


def _helper_prompt_needs_retry(prompt_output: str) -> bool:
    stripped = prompt_output.strip()
    if not stripped:
        return True
    compact = "".join(stripped.split())
    return len(compact) < _HELPER_PROMPT_MIN_CHARS or stripped.endswith(_HELPER_PROMPT_DANGLING_SUFFIXES)


def _build_helper_retry_prompt(user_prompt: str, previous_output: str, type_zh: str) -> str:
    return (
        f"{user_prompt}\n\n"
        "上次輸出太短或像半句，不能使用。\n"
        f"上次輸出：{previous_output}\n"
        f"請重新為該{type_zh}輸出一段完整、可直接使用的繁體中文提示詞。"
        "至少 50 個中文字，必須是完整句子，不要只輸出片語。"
    )


def _compact_helper_context_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def _truncate_helper_context_text(value: Any) -> str:
    text = _compact_helper_context_text(value)
    if len(text) <= _HELPER_LOREBOOK_DESC_MAX_CHARS:
        return text
    return text[: _HELPER_LOREBOOK_DESC_MAX_CHARS - 3].rstrip() + "..."


def _build_helper_lorebook_line(name: Any, data: Any, extra_fields: tuple[tuple[str, str], ...]) -> str:
    entry_name = _compact_helper_context_text(name) or str(name).strip()
    if not entry_name:
        return ""

    description = ""
    extras: list[str] = []
    if isinstance(data, dict):
        description = _truncate_helper_context_text(data.get("description"))
        for field, label in extra_fields:
            value = _truncate_helper_context_text(data.get(field))
            if value:
                extras.append(f"{label}: {value}")
    elif isinstance(data, str):
        description = _truncate_helper_context_text(data)

    line = f"- {entry_name}"
    if description:
        line += f"：{description}"
    if extras:
        line += f"（{'；'.join(extras)}）"
    return line


def _format_helper_lorebook_section(
    title: str,
    entries: Any,
    extra_fields: tuple[tuple[str, str], ...] = (),
) -> str:
    if not isinstance(entries, dict) or not entries:
        return ""

    lines: list[str] = []
    for name, data in entries.items():
        line = _build_helper_lorebook_line(name, data, extra_fields)
        if line:
            lines.append(line)
        if len(lines) >= _HELPER_LOREBOOK_MAX_ENTRIES:
            break

    if not lines:
        return ""
    return f"{title}:\n" + "\n".join(lines)


def _build_helper_lorebook_context(project: dict[str, Any]) -> str:
    sections = [
        _format_helper_lorebook_section(title, project.get(key), extra_fields)
        for title, key, extra_fields in _HELPER_LOREBOOK_SECTIONS
    ]
    return "\n\n".join(section for section in sections if section)


def _build_helper_user_prompt(project: dict[str, Any], req: OptimizePromptRequest, type_zh: str) -> str:
    project_overview = project.get("overview", {})
    if not isinstance(project_overview, dict):
        project_overview = {}

    project_style = _compact_helper_context_text(project.get("style"))
    project_style_description = _compact_helper_context_text(project.get("style_description"))
    project_style_image = _compact_helper_context_text(project.get("style_image"))
    genre = _compact_helper_context_text(project_overview.get("genre"))
    synopsis = _compact_helper_context_text(project_overview.get("synopsis"))
    lorebook_context = _build_helper_lorebook_context(project)

    user_content = [
        f"專案故事大綱: {synopsis}" if synopsis else "",
        f"專案題材類型: {genre}" if genre else "",
        f"整體視覺風格: {project_style}" if project_style else "",
        f"專案風格描述: {project_style_description}" if project_style_description else "",
        f"專案風格參考圖: {project_style_image}" if project_style_image else "",
        lorebook_context,
        f"實體類型: {type_zh}",
        f"名稱: {req.name}" if req.name else "",
        f"基本描述/分鏡旁白內容: {req.description}",
        f"額外指示: {req.instruction}" if req.instruction else "",
        _HELPER_SOURCE_PRIORITY_RULE,
        f"請為該{type_zh}生成對應的提示詞：",
    ]
    return "\n".join([line for line in user_content if line])


def _build_helper_system_prompt(is_video: bool) -> str:
    kind = "Text-to-Video" if is_video else "Text-to-Image"
    focus = (
        "4. 著重於描述主體動作、相機運動（如 推近、向右橫搖）、光影變化與動態效果。"
        if is_video
        else "4. 根據提供的專案視覺風格進行渲染，描述畫面構圖、光影與物件細節。"
    )
    return (
        "你是一個專業的 AI 繪圖與影片動作提示詞生成助手。\n"
        f"你的任務是根據使用者提供的基本描述、專案故事背景與整體風格，生成一段精緻、細節豐富、適合 {kind} 模型的繁體中文提示詞（Prompt）。\n"
        "【規則】\n"
        f"1. {helper_prompt_language_clause()}\n"
        "2. 請直接輸出 Prompt 本身，不要包含 markdown 格式、引號、任何前綴或額外的解釋文字。\n"
        "3. 長度控制在 50 至 120 個字之間。\n"
        f"{focus}"
    )


@router.post("/projects/{project_name}/helper/generate-prompt")
async def helper_generate_prompt(
    project_name: str,
    req: OptimizePromptRequest,
    _user: CurrentUser,
):
    """
    調用 AI 文字生成服務，為角色、道具、場景、分鏡圖或影片生成/最佳化提示詞（Prompt）。
    """
    type_zh = _HELPER_TYPE_LABELS.get(req.type)
    if type_zh is None:
        raise HTTPException(
            status_code=400,
            detail="不支援的類型。必須是 'character'、'clue'、'scene'、'image_prompt' 或 'video_prompt'",
        )

    try:
        from lib.text_backends.base import TextGenerationRequest, TextTaskType
        from lib.text_generator import TextGenerator

        # 載入專案 overview 與設定集，使生成的 prompt 更契合專案
        project = get_project_manager().load_project(project_name)

        is_video = req.type == "video_prompt"
        system_prompt = _build_helper_system_prompt(is_video)
        user_prompt = _build_helper_user_prompt(project, req, type_zh)

        if req.model:
            generator = await TextGenerator.create_with_model_str(req.model)
        else:
            generator = await TextGenerator.create(TextTaskType.OVERVIEW, project_name)
        result = await generator.generate(
            TextGenerationRequest(
                prompt=user_prompt,
                system_prompt=system_prompt,
                max_output_tokens=300,
            ),
            project_name=project_name,
        )

        prompt_output = _clean_helper_prompt(result.text)
        if _helper_prompt_needs_retry(prompt_output):
            retry_result = await generator.generate(
                TextGenerationRequest(
                    prompt=_build_helper_retry_prompt(user_prompt, prompt_output, type_zh),
                    system_prompt=system_prompt,
                    max_output_tokens=500,
                ),
                project_name=project_name,
            )
            retry_output = _clean_helper_prompt(retry_result.text)
            if not _helper_prompt_needs_retry(retry_output) or len(retry_output) > len(prompt_output):
                prompt_output = retry_output

        return {
            "success": True,
            "prompt": prompt_output,
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"專案 '{project_name}' 不存在")
    except Exception as e:
        logger.exception("AI 提示詞生成失敗")
        raise HTTPException(status_code=500, detail=str(e))
