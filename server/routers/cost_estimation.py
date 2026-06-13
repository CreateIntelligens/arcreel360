"""費用估算 API 路由。"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from lib import PROJECT_ROOT
from lib.config.resolver import ConfigResolver
from lib.cost_calculator import CostCalculator
from lib.db import async_session_factory
from lib.episode_overrides import read_episode_override as _read_episode_override
from lib.project_manager import ProjectManager
from lib.providers import CallType, normalize_provider_id
from lib.storyboard_sequence import find_storyboard_item, get_storyboard_items
from lib.usage_tracker import UsageTracker
from server.auth import CurrentUser
from server.services.cost_estimation import CostEstimationService

router = APIRouter()
logger = logging.getLogger(__name__)
pm = ProjectManager(PROJECT_ROOT / "projects")


@router.get("/projects/{project_name}/cost-estimate")
async def get_cost_estimate(project_name: str, _user: CurrentUser):
    """獲取專案費用估算（預估 + 實際）。"""

    def _sync():
        if not pm.project_exists(project_name):
            raise HTTPException(status_code=404, detail=f"專案 '{project_name}' 不存在")

        try:
            project_data = pm.load_project(project_name)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"專案 '{project_name}' 不存在")

        # 載入所有劇本
        scripts: dict[str, dict] = {}
        for ep in project_data.get("episodes", []):
            script_file = ep.get("script_file", "")
            if script_file:
                try:
                    scripts[script_file] = pm.load_script(project_name, script_file)
                except FileNotFoundError:
                    logger.debug("劇本檔案不存在，跳過: %s/%s", project_name, script_file)

        return project_data, scripts

    project_data, scripts = await asyncio.to_thread(_sync)

    resolver = ConfigResolver(async_session_factory)
    tracker = UsageTracker(session_factory=async_session_factory)
    service = CostEstimationService(resolver, tracker)

    try:
        return await service.compute(project_data, scripts, project_name=project_name)
    except Exception:
        logger.exception("費用估算失敗")
        raise HTTPException(status_code=500, detail="費用估算失敗，請稍後重試")


class SceneCostEstimateRequest(BaseModel):
    project_name: str
    script_file: str
    scene_id: str
    # 候選 backend；null = 沿用上層（與 scene 當前覆蓋對齊）
    image_backend: str | None = None
    video_backend: str | None = None


def _parse_backend(raw: str | None) -> tuple[str | None, str | None]:
    if not raw:
        return None, None
    if "/" in raw:
        provider, model = raw.split("/", 1)
        return provider, model
    return raw, None


def _resolve_effective(
    scene_value: str | None,
    episode_value: str | None,
    project_value: str | None,
    default_provider: str | None,
    default_model: str | None,
) -> tuple[str | None, str | None]:
    """scene → episode → project → global default 四層回退。"""
    for raw in (scene_value, episode_value, project_value):
        provider, model = _parse_backend(raw)
        if provider:
            return provider, model
    return default_provider, default_model


def _cost(
    calculator: CostCalculator,
    provider: str | None,
    model: str | None,
    call_type: CallType,
    *,
    duration: int,
    resolution: str | None = None,
) -> tuple[float, str]:
    if not provider:
        return 0.0, "USD"
    return calculator.calculate_cost(
        provider=normalize_provider_id(provider),
        call_type=call_type,
        model=model,
        duration_seconds=duration,
        resolution=resolution,
    )


def _project_video_resolution(project: dict, model: str | None) -> str | None:
    """從 project.video_model_settings[model].resolution 讀解析度。"""
    if not model:
        return None
    settings = project.get("video_model_settings")
    if not isinstance(settings, dict):
        return None
    model_settings = settings.get(model)
    if not isinstance(model_settings, dict):
        return None
    resolution = model_settings.get("resolution")
    return resolution if isinstance(resolution, str) and resolution else None


def _resolve_duration(project: dict, scene: dict, script_file: str) -> int:
    duration = scene.get("duration_seconds")
    if duration is None:
        duration = _read_episode_override(project, script_file, "duration_seconds")
    if duration is None:
        duration = project.get("default_duration")
    return int(duration if duration is not None else 8)


def _resolve_video_resolution(project: dict, scene: dict, script_file: str, model: str | None) -> str | None:
    return (
        scene.get("video_resolution")
        or _read_episode_override(project, script_file, "video_resolution")
        or _project_video_resolution(project, model)
    )


def _cost_breakdown(current: float, next_value: float, currency: str) -> dict:
    return {
        "current": current,
        "next": next_value,
        "delta": next_value - current,
        "currency": currency,
    }


def _load_scene_cost_context(project_name: str, script_file: str, scene_id: str) -> tuple[dict, dict, int]:
    if not pm.project_exists(project_name):
        raise HTTPException(status_code=404, detail=f"專案 '{project_name}' 不存在")
    project = pm.load_project(project_name)
    try:
        script = pm.load_script(project_name, script_file)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"劇本 '{script_file}' 不存在")

    items, id_field, _, _, _ = get_storyboard_items(script)
    resolved = find_storyboard_item(items, id_field, scene_id)
    if resolved is None:
        raise HTTPException(status_code=404, detail=f"分鏡 '{scene_id}' 不存在")

    scene, _ = resolved
    return project, scene, _resolve_duration(project, scene, script_file)


@router.post("/cost-estimation/scene")
async def estimate_scene_cost(req: SceneCostEstimateRequest, _user: CurrentUser):
    """計算 scene 在套用候選 backend 後的費用差異。

    回傳 image / video 各自 { current, next, delta, currency }。
    """
    project, scene, duration = await asyncio.to_thread(
        _load_scene_cost_context,
        req.project_name,
        req.script_file,
        req.scene_id,
    )

    resolver = ConfigResolver(async_session_factory)
    async with resolver.session() as r:
        default_img_provider, default_img_model = await r.default_image_backend()
        default_vid_provider, default_vid_model = await r.default_video_backend()

    project_img = project.get("image_backend")
    project_vid = project.get("video_backend")
    scene_img = scene.get("image_backend")
    scene_vid = scene.get("video_backend")

    episode_img = _read_episode_override(project, req.script_file, "image_backend")
    episode_vid = _read_episode_override(project, req.script_file, "video_backend")

    # current：使用當前 scene 設定
    cur_img_p, cur_img_m = _resolve_effective(
        scene_img, episode_img, project_img, default_img_provider, default_img_model
    )
    cur_vid_p, cur_vid_m = _resolve_effective(
        scene_vid, episode_vid, project_vid, default_vid_provider, default_vid_model
    )

    # next：使用 request 候選值取代 scene 層
    next_img_p, next_img_m = _resolve_effective(
        req.image_backend, episode_img, project_img, default_img_provider, default_img_model
    )
    next_vid_p, next_vid_m = _resolve_effective(
        req.video_backend, episode_vid, project_vid, default_vid_provider, default_vid_model
    )

    calculator = CostCalculator()
    cur_vid_res = _resolve_video_resolution(project, scene, req.script_file, cur_vid_m)
    next_vid_res = _resolve_video_resolution(project, scene, req.script_file, next_vid_m)

    img_cur, img_currency = _cost(calculator, cur_img_p, cur_img_m, "image", duration=duration)
    img_next, _ = _cost(calculator, next_img_p, next_img_m, "image", duration=duration)
    vid_cur, vid_currency = _cost(calculator, cur_vid_p, cur_vid_m, "video", duration=duration, resolution=cur_vid_res)
    vid_next, _ = _cost(calculator, next_vid_p, next_vid_m, "video", duration=duration, resolution=next_vid_res)

    return {
        "scene_id": req.scene_id,
        "duration_seconds": duration,
        "image": _cost_breakdown(img_cur, img_next, img_currency),
        "video": _cost_breakdown(vid_cur, vid_next, vid_currency),
    }
