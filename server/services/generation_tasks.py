"""
Task execution service for queued generation jobs.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lib.config.resolver import ConfigResolver

from lib import PROJECT_ROOT
from lib.config.registry import PROVIDER_REGISTRY
from lib.custom_provider import is_custom_provider
from lib.db.base import DEFAULT_USER_ID
from lib.gemini_shared import get_shared_rate_limiter
from lib.media_generator import MediaGenerator
from lib.project_change_hints import emit_project_change_batch, project_change_source
from lib.project_manager import ProjectManager
from lib.prompt_builders import build_character_prompt, build_clue_prompt, build_scene_prompt, build_style_prompt
from lib.prompt_utils import (
    image_prompt_to_yaml,
    is_structured_image_prompt,
    is_structured_video_prompt,
    video_prompt_to_yaml,
)
from lib.providers import (
    PROVIDER_AI360,
    PROVIDER_BYTEPLUS,
    PROVIDER_GEMINI,
    PROVIDER_GROK,
    PROVIDER_OPENAI,
    normalize_provider_id,
)
from lib.storyboard_sequence import (
    build_previous_storyboard_reference,
    find_storyboard_item,
    get_storyboard_items,
    resolve_previous_storyboard_path,
)
from lib.thumbnail import extract_video_thumbnail

pm = ProjectManager(PROJECT_ROOT / "projects")
rate_limiter = get_shared_rate_limiter()
logger = logging.getLogger(__name__)

# 按 (channel, provider_name, model) 快取 Backend 例項，避免每次任務重建 API 客戶端
_backend_cache: dict[tuple[str, ...], Any] = {}

# 各供應商預設影片解析度
DEFAULT_VIDEO_RESOLUTION: dict[str, str] = {
    PROVIDER_GEMINI: "1080p",
    PROVIDER_BYTEPLUS: "720p",
    PROVIDER_GROK: "720p",
    PROVIDER_OPENAI: "720p",
}

# provider_id → backend registry name 的對映
_PROVIDER_ID_TO_BACKEND: dict[str, str] = {
    "gemini-aistudio": PROVIDER_GEMINI,
    "gemini-vertex": PROVIDER_GEMINI,
    PROVIDER_GEMINI: PROVIDER_GEMINI,
    "ark": PROVIDER_BYTEPLUS,
    "seedance": PROVIDER_BYTEPLUS,
    PROVIDER_BYTEPLUS: PROVIDER_BYTEPLUS,
    PROVIDER_GROK: PROVIDER_GROK,
    PROVIDER_OPENAI: PROVIDER_OPENAI,
    PROVIDER_AI360: PROVIDER_AI360,
}


def get_project_manager() -> ProjectManager:
    return pm


def invalidate_backend_cache() -> None:
    """清空 VideoBackend 例項快取。在配置變更後呼叫。"""
    _backend_cache.clear()


def _parse_project_backend(raw: str | None) -> tuple[str | None, str | None]:
    """解析 project.json 中 ``video_backend`` / ``image_backend`` 的 ``"provider/model"`` 格式。"""
    if not raw:
        return None, None
    if "/" in raw:
        provider, model = raw.split("/", 1)
        return provider, model
    return raw, None


async def _create_custom_backend(provider_name: str, model_id: str | None, media_type: str):
    """自定義供應商的 backend 建立路徑。"""
    from lib.custom_provider import parse_provider_id
    from lib.custom_provider.factory import create_custom_backend
    from lib.db import async_session_factory
    from lib.db.repositories.custom_provider_repo import CustomProviderRepository

    async with async_session_factory() as session:
        repo = CustomProviderRepository(session)
        db_id = parse_provider_id(provider_name)
        provider = await repo.get_provider(db_id)
        if provider is None:
            raise ValueError(f"自定義供應商 {provider_name} 不存在")
        if model_id:
            # 校驗 model_id 仍存在且已啟用，否則回退到預設模型
            from sqlalchemy import select

            from lib.db.models.custom_provider import CustomProviderModel

            stmt = select(CustomProviderModel).where(
                CustomProviderModel.provider_id == db_id,
                CustomProviderModel.model_id == model_id,
                CustomProviderModel.media_type == media_type,
                CustomProviderModel.is_enabled == True,  # noqa: E712
            )
            result = await session.execute(stmt)
            if result.scalar_one_or_none() is None:
                logger.warning("自定義模型 %s/%s 已不存在或已禁用，回退到預設模型", provider_name, model_id)
                model_id = None

        if not model_id:
            default_model = await repo.get_default_model(db_id, media_type)
            if default_model:
                model_id = default_model.model_id
            else:
                raise ValueError(f"自定義供應商 {provider_name} 沒有預設 {media_type} 模型")
        return create_custom_backend(provider=provider, model_id=model_id, media_type=media_type)


async def _get_or_create_video_backend(
    provider_name: str,
    provider_settings: dict,
    resolver: ConfigResolver,
    *,
    default_video_model: str | None = None,
):
    """獲取或建立 VideoBackend 例項（帶快取）。

    provider_name 可以是舊格式（gemini/seedance/ark/grok）或新格式（gemini-aistudio/gemini-vertex/byteplus）。
    透過 resolver 按需載入供應商配置。
    default_video_model: 全域性預設影片模型，當 provider_settings 中無 model 時作為 fallback。
    """
    from lib.video_backends import create_backend

    provider_name = normalize_provider_id(provider_name)
    effective_model = provider_settings.get("model") or default_video_model or None

    # BytePlus (Ark) 供應商適配：如果 model 不是以 ep- 開頭，自動嘗試載入配置中的 endpoint_id
    if provider_name == PROVIDER_BYTEPLUS and effective_model and not effective_model.startswith("ep-"):
        async with resolver._open_session() as (session, svc):
            endpoint_id = await svc.get_setting("byteplus_video_endpoint_id", "")
        if endpoint_id:
            logger.info("自動將火山引擎預置模型 %s 替換為接入點 %s", effective_model, endpoint_id)
            effective_model = endpoint_id

    cache_key = ("video", provider_name, effective_model)
    if cache_key in _backend_cache:
        return _backend_cache[cache_key]

    # 自定義供應商走獨立工廠路徑
    if is_custom_provider(provider_name):
        backend = await _create_custom_backend(provider_name, effective_model, "video")
        _backend_cache[cache_key] = backend
        return backend

    # 解析 provider_id → backend registry name
    backend_name = _PROVIDER_ID_TO_BACKEND.get(provider_name, provider_name)

    kwargs: dict = {}
    if backend_name == PROVIDER_GEMINI:
        # 確定 backend_type（aistudio 或 vertex）
        if provider_name == "gemini-vertex":
            kwargs["backend_type"] = "vertex"
        elif provider_name == "gemini-aistudio":
            kwargs["backend_type"] = "aistudio"
        else:
            kwargs["backend_type"] = "aistudio"

        config_provider_id = "gemini-vertex" if kwargs["backend_type"] == "vertex" else "gemini-aistudio"
        db_config = await resolver.provider_config(config_provider_id)
        kwargs["api_key"] = db_config.get("api_key")
        kwargs["rate_limiter"] = rate_limiter
        kwargs["video_model"] = effective_model
    elif backend_name == PROVIDER_AI360:
        # ai360 以帳密登入，需傳 username/password/base_url/project_id（與簡單供應商不同）
        db_config = await resolver.provider_config(PROVIDER_AI360)
        kwargs["username"] = db_config.get("username")
        kwargs["password"] = db_config.get("api_key")  # password 存於 credential 表的 api_key 欄
        kwargs["base_url"] = db_config.get("base_url")
        kwargs["project_id"] = db_config.get("project_id")
        kwargs["model"] = effective_model
    else:
        await _fill_simple_provider_kwargs(backend_name, resolver, kwargs, effective_model)

    backend = create_backend(backend_name, **kwargs)
    _backend_cache[cache_key] = backend
    return backend


async def _fill_simple_provider_kwargs(
    backend_name: str,
    resolver: ConfigResolver,
    kwargs: dict,
    effective_model: str | None,
) -> None:
    """BytePlus/Grok/OpenAI 等簡單供應商的通用配置填充。"""
    db_config = await resolver.provider_config(backend_name)
    kwargs["api_key"] = db_config.get("api_key")
    kwargs["model"] = effective_model
    if base_url := db_config.get("base_url"):
        kwargs["base_url"] = base_url


async def _get_or_create_image_backend(
    provider_name: str,
    provider_settings: dict,
    resolver: ConfigResolver,
    *,
    default_image_model: str | None = None,
):
    """獲取或建立 ImageBackend 例項（帶快取）。"""
    from lib.image_backends import create_backend

    provider_name = normalize_provider_id(provider_name)
    effective_model = provider_settings.get("model") or default_image_model or None
    cache_key = ("image", provider_name, effective_model)
    if cache_key in _backend_cache:
        return _backend_cache[cache_key]

    # 自定義供應商走獨立工廠路徑
    if is_custom_provider(provider_name):
        backend = await _create_custom_backend(provider_name, effective_model, "image")
        _backend_cache[cache_key] = backend
        return backend

    backend_name = _PROVIDER_ID_TO_BACKEND.get(provider_name, provider_name)

    kwargs: dict = {}
    if backend_name == PROVIDER_GEMINI:
        if provider_name == "gemini-vertex":
            kwargs["backend_type"] = "vertex"
        else:
            kwargs["backend_type"] = "aistudio"
        config_id = "gemini-vertex" if kwargs["backend_type"] == "vertex" else "gemini-aistudio"
        db_config = await resolver.provider_config(config_id)
        kwargs["api_key"] = db_config.get("api_key")
        kwargs["base_url"] = db_config.get("base_url")
        kwargs["rate_limiter"] = rate_limiter
        kwargs["image_model"] = effective_model
    else:
        await _fill_simple_provider_kwargs(backend_name, resolver, kwargs, effective_model)

    backend = create_backend(backend_name, **kwargs)
    _backend_cache[cache_key] = backend
    return backend


async def _resolve_video_backend(
    project_name: str,
    resolver: ConfigResolver,
    payload: dict | None,
) -> tuple[Any | None, str, str]:
    """解析影片後端，返回 (video_backend, video_backend_type, video_model)。

    僅在 payload 存在時建立 VideoBackend，避免圖片任務因影片配置缺失而報錯。
    注意：video_backend_type 僅在 video_backend 為 None（回退到 GeminiClient）時生效，
    因此只需要在全域性預設回退分支中設定。
    """
    default_video_provider_id, video_model = await resolver.default_video_backend()
    video_backend = None
    video_backend_type = "aistudio"

    if payload:
        # 優先序：payload 分鏡覆蓋 > project.json > 全域性預設
        payload_provider = payload.get("video_provider")
        payload_model = (payload.get("video_provider_settings") or {}).get("model")

        if payload_provider:
            provider_name = payload_provider
            project_model = payload_model
        else:
            project = await asyncio.to_thread(get_project_manager().load_project, project_name)
            provider_name, project_model = _parse_project_backend(project.get("video_backend"))

        if not provider_name:
            provider_name = default_video_provider_id
            mapped = _PROVIDER_ID_TO_BACKEND.get(provider_name, provider_name)
            if mapped == PROVIDER_GEMINI:
                video_backend_type = "vertex" if default_video_provider_id == "gemini-vertex" else "aistudio"

        provider_settings: dict = {"model": project_model} if project_model else {}
        video_backend = await _get_or_create_video_backend(
            provider_name,
            provider_settings,
            resolver,
            default_video_model=video_model,
        )

    return video_backend, video_backend_type, video_model


async def get_media_generator(
    project_name: str,
    payload: dict | None = None,
    *,
    user_id: str = DEFAULT_USER_ID,
    require_image_backend: bool = True,
) -> MediaGenerator:
    """建立 MediaGenerator。僅按呼叫場景初始化所需的 backend。"""
    from lib.config.resolver import ConfigResolver
    from lib.db import async_session_factory

    project_path = await asyncio.to_thread(get_project_manager().get_project_path, project_name)
    resolver = ConfigResolver(async_session_factory)

    # 初始化階段共享單一 session
    async with resolver.session() as r:
        image_backend = None
        if require_image_backend:
            image_provider_id, image_model = await r.default_image_backend()
            # payload 中的 image_provider（由入隊時 _snapshot_image_backend 注入）
            if payload and payload.get("image_provider"):
                image_provider_id = payload["image_provider"]
                image_model = payload.get("image_model", "") or image_model
            else:
                # 直接從 project.json 的 image_backend（"provider/model" 格式）讀取
                project = await asyncio.to_thread(get_project_manager().load_project, project_name)
                proj_provider, proj_model = _parse_project_backend(project.get("image_backend"))
                if proj_provider:
                    # 僅當 provider 相同時才複用全域性預設 model，避免跨 provider model 不匹配
                    image_model = proj_model or (image_model if proj_provider == image_provider_id else None)
                    image_provider_id = proj_provider
            image_backend = await _get_or_create_image_backend(
                image_provider_id,
                {},
                r,
                default_image_model=image_model,
            )

        # 解析 video backend（保持現有邏輯）
        video_backend, _, _ = await _resolve_video_backend(
            project_name,
            r,
            payload,
        )

    # 傳原始 resolver 給 MediaGenerator（後續呼叫在 session scope 外）
    return MediaGenerator(
        project_path,
        rate_limiter=rate_limiter,
        image_backend=image_backend,
        video_backend=video_backend,
        config_resolver=resolver,
        user_id=user_id,
    )


def get_aspect_ratio(project: dict, resource_type: str) -> str:
    if resource_type == "characters":
        return "3:4"
    if resource_type == "clues":
        return "16:9"
    # 優先讀頂層欄位；缺失時按 content_mode 推導（向後相容）
    val = project.get("aspect_ratio")
    if isinstance(val, str):
        return val
    if isinstance(val, dict) and resource_type in val:
        return val[resource_type]
    return "9:16" if project.get("content_mode", "narration") == "narration" else "16:9"


def _normalize_storyboard_prompt(prompt: str | dict, style: str) -> str:
    if isinstance(prompt, str):
        if style:
            return f"{style}\n\n{prompt}"
        return prompt

    if not isinstance(prompt, dict):
        raise ValueError("prompt must be a string or object")

    if not is_structured_image_prompt(prompt):
        raise ValueError("prompt must be a string or include scene/composition")

    scene_text = str(prompt.get("scene", "")).strip()
    if not scene_text:
        raise ValueError("prompt.scene must not be empty")

    composition = prompt.get("composition") if isinstance(prompt.get("composition"), dict) else {}
    normalized_prompt = {
        "scene": scene_text,
        "composition": {
            "shot_type": str(composition.get("shot_type") or "Medium Shot"),
            "lighting": str(composition.get("lighting", "") or ""),
            "ambiance": str(composition.get("ambiance", "") or ""),
        },
    }
    return image_prompt_to_yaml(normalized_prompt, style)


def _normalize_video_prompt(prompt: str | dict) -> str:
    if isinstance(prompt, str):
        return prompt

    if not isinstance(prompt, dict):
        raise ValueError("prompt must be a string or object")

    if not is_structured_video_prompt(prompt):
        raise ValueError("prompt must be a string or include action/camera_motion")

    action_text = str(prompt.get("action", "")).strip()
    if not action_text:
        raise ValueError("prompt.action must not be empty")

    dialogue = prompt.get("dialogue", [])
    if dialogue is None:
        dialogue = []
    if not isinstance(dialogue, list):
        raise ValueError("prompt.dialogue must be an array")

    normalized_dialogue = []
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        speaker = str(item.get("speaker", "") or "").strip()
        line = str(item.get("line", "") or "").strip()
        if speaker or line:
            normalized_dialogue.append({"speaker": speaker, "line": line})

    normalized_prompt: dict[str, Any] = {
        "action": action_text,
        "camera_motion": str(prompt.get("camera_motion", "") or "") or "Static",
        "ambiance_audio": str(prompt.get("ambiance_audio", "") or ""),
        "dialogue": normalized_dialogue,
    }
    return video_prompt_to_yaml(normalized_prompt)


def _get_model_default_duration(provider_name: str, model_name: str | None) -> int:
    """從 PROVIDER_REGISTRY 查詢模型的 supported_durations[0]，找不到則 fallback 4。"""
    provider_meta = PROVIDER_REGISTRY.get(provider_name)
    if provider_meta and model_name:
        model_info = provider_meta.models.get(model_name)
        if model_info and model_info.supported_durations:
            return model_info.supported_durations[0]
    # 自定義供應商或 registry 中無此模型時 fallback
    return 4


def _append_existing_project_asset(reference_images: list[object], project_path: Path, asset_path: str | None) -> None:
    if not asset_path:
        return
    path = project_path / asset_path
    if path.exists():
        reference_images.append(path)


def _append_entity_reference_images(
    reference_images: list[object],
    project_path: Path,
    entities: dict,
    names: list[str],
    sheet_fields: tuple[str, ...],
) -> None:
    for name in names:
        entity_data = entities.get(name, {})
        sheet = next((entity_data.get(field) for field in sheet_fields if entity_data.get(field)), None)
        _append_existing_project_asset(reference_images, project_path, sheet)


def _collect_reference_images(
    project: dict,
    project_path: Path,
    target_item: dict,
    *,
    char_field: str,
    clue_field: str,
    scene_field: str | None = None,
    extra_reference_images: list[str] | None = None,
    previous_storyboard_path: Path | None = None,
) -> list[object] | None:
    reference_images: list[object] = []

    _append_entity_reference_images(
        reference_images,
        project_path,
        project.get("characters", {}),
        target_item.get(char_field, []),
        ("character_sheet",),
    )
    _append_entity_reference_images(
        reference_images,
        project_path,
        project.get("clues", {}),
        target_item.get(clue_field, []),
        ("clue_sheet",),
    )

    if scene_field:
        scene_name = target_item.get(scene_field)
        if scene_name:
            _append_entity_reference_images(
                reference_images,
                project_path,
                project.get("scenes", {}),
                [scene_name],
                ("scene_sheet", "scene_ref"),
            )

    for extra in extra_reference_images or []:
        extra_path = Path(extra)
        if not extra_path.is_absolute():
            extra_path = project_path / extra_path
        if extra_path.exists():
            reference_images.append(extra_path)

    if previous_storyboard_path and previous_storyboard_path.exists():
        reference_images.append(build_previous_storyboard_reference(previous_storyboard_path))

    # 納入本分鏡自己的參考圖（v0 基底）
    storyboard_sheet = target_item.get("storyboard_sheet")
    if storyboard_sheet:
        _append_existing_project_asset(reference_images, project_path, storyboard_sheet)
    else:
        storyboard_ref = target_item.get("reference_image")
        if storyboard_ref:
            _append_existing_project_asset(reference_images, project_path, storyboard_ref)

    return reference_images or None


def _resolve_script_episode(project_name: str, script_file: str | None) -> int | None:
    if not script_file:
        return None
    try:
        script = get_project_manager().load_script(project_name, script_file)
    except Exception:
        return None

    episode = script.get("episode")
    if isinstance(episode, int):
        return episode
    return None


def _require_item_prompt(
    payload_prompt: Any,
    target_item: dict[str, Any],
    prompt_key: str,
    resource_id: str,
) -> Any:
    """Return payload prompt, falling back to the script item for batch queued tasks."""
    effective_prompt = payload_prompt or target_item.get(prompt_key)
    if not effective_prompt:
        raise ValueError(f"{prompt_key} missing for {resource_id}")
    return effective_prompt


def _resolve_storyboard_item(script: dict[str, Any], resource_id: str) -> tuple[dict, list[dict], str, str, str, str]:
    """Resolve a narration segment or drama scene from a storyboard-compatible script."""
    items, id_field, char_field, clue_field, scene_field = get_storyboard_items(script)
    resolved = find_storyboard_item(items, id_field, resource_id)
    if resolved is None:
        raise ValueError(f"scene/segment not found: {resource_id}")
    target_item, _ = resolved
    return target_item, items, id_field, char_field, clue_field, scene_field


def _compute_affected_fingerprints(project_name: str, task_type: str, resource_id: str) -> dict[str, int]:
    """計算受影響檔案的 mtime 指紋"""
    try:
        project_path = get_project_manager().get_project_path(project_name)
    except Exception:
        return {}

    paths: list[tuple[str, Path]] = []

    if task_type == "storyboard":
        paths.append(
            (
                f"storyboards/scene_{resource_id}.png",
                project_path / "storyboards" / f"scene_{resource_id}.png",
            )
        )
    elif task_type == "video":
        paths.append(
            (
                f"videos/scene_{resource_id}.mp4",
                project_path / "videos" / f"scene_{resource_id}.mp4",
            )
        )
        paths.append(
            (
                f"thumbnails/scene_{resource_id}.jpg",
                project_path / "thumbnails" / f"scene_{resource_id}.jpg",
            )
        )
    elif task_type == "character":
        paths.append(
            (
                f"characters/{resource_id}.png",
                project_path / "characters" / f"{resource_id}.png",
            )
        )
    elif task_type == "clue":
        paths.append(
            (
                f"clues/{resource_id}.png",
                project_path / "clues" / f"{resource_id}.png",
            )
        )

    result: dict[str, int] = {}
    for rel, abs_path in paths:
        if abs_path.exists():
            result[rel] = abs_path.stat().st_mtime_ns

    return result


# (entity_type, action, label_tpl, include_script_episode)
_TASK_CHANGE_SPECS: dict[str, tuple] = {
    "storyboard": ("segment", "storyboard_ready", "分鏡「{}」", True),
    "video": ("segment", "video_ready", "分鏡「{}」", True),
    "character": ("character", "updated", "角色「{}」設計圖", False),
    "clue": ("clue", "updated", "道具「{}」設計圖", False),
}


def _emit_generation_success_batch(
    *,
    task_type: str,
    project_name: str,
    resource_id: str,
    payload: dict[str, Any],
) -> None:
    spec = _TASK_CHANGE_SPECS.get(task_type)
    if spec is None:
        return

    entity_type, action, label_tpl, include_script_episode = spec
    asset_fingerprints = _compute_affected_fingerprints(project_name, task_type, resource_id)

    change: dict[str, Any] = {
        "entity_type": entity_type,
        "action": action,
        "entity_id": resource_id,
        "label": label_tpl.format(resource_id),
        "focus": None,
        "important": True,
        "asset_fingerprints": asset_fingerprints,
    }
    if include_script_episode:
        script_file = str(payload.get("script_file") or "") or None
        change["script_file"] = script_file
        change["episode"] = _resolve_script_episode(project_name, script_file)

    try:
        emit_project_change_batch(project_name, [change], source="worker")
    except Exception:
        logger.exception(
            "傳送生成完成專案事件失敗 project=%s task_type=%s resource_id=%s",
            project_name,
            task_type,
            resource_id,
        )


async def execute_storyboard_task(
    project_name: str, resource_id: str, payload: dict[str, Any], *, user_id: str = DEFAULT_USER_ID
) -> dict[str, Any]:
    script_file = payload.get("script_file")
    if not script_file:
        raise ValueError("script_file is required for storyboard task")

    prompt = payload.get("prompt")

    def _prepare():
        _manager = get_project_manager()
        _project = _manager.load_project(project_name)
        _project_path = _manager.get_project_path(project_name)
        _script = _manager.load_script(project_name, script_file)
        _target_item, _items, _id_field, _char_field, _clue_field, _scene_field = _resolve_storyboard_item(
            _script, resource_id
        )

        _effective_prompt = _require_item_prompt(prompt, _target_item, "image_prompt", resource_id)
        _prev_path = resolve_previous_storyboard_path(_project_path, _items, _id_field, resource_id)
        _combined_style = build_style_prompt(_project)
        _prompt_text = _normalize_storyboard_prompt(_effective_prompt, _combined_style)
        _ref_images = _collect_reference_images(
            _project,
            _project_path,
            _target_item,
            char_field=_char_field,
            clue_field=_clue_field,
            scene_field=_scene_field,
            extra_reference_images=payload.get("extra_reference_images") or [],
            previous_storyboard_path=_prev_path,
        )
        return _project, _project_path, _prompt_text, _ref_images

    project, project_path, prompt_text, reference_images = await asyncio.to_thread(_prepare)

    generator = await get_media_generator(
        project_name,
        payload=payload,
        user_id=user_id,
    )
    aspect_ratio = get_aspect_ratio(project, "storyboards")

    _, version = await generator.generate_image_async(
        prompt=prompt_text,
        resource_type="storyboards",
        resource_id=resource_id,
        reference_images=reference_images,
        aspect_ratio=aspect_ratio,
        image_size=payload.get("image_size") or "1K",
    )

    def _finalize():
        get_project_manager().update_scene_asset(
            project_name=project_name,
            script_filename=script_file,
            scene_id=resource_id,
            asset_type="storyboard_image",
            asset_path=f"storyboards/scene_{resource_id}.png",
        )
        return generator.versions.get_versions("storyboards", resource_id)["versions"][-1]["created_at"]

    created_at = await asyncio.to_thread(_finalize)

    return {
        "version": version,
        "file_path": f"storyboards/scene_{resource_id}.png",
        "created_at": created_at,
        "resource_type": "storyboards",
        "resource_id": resource_id,
    }


async def execute_video_task(
    project_name: str, resource_id: str, payload: dict[str, Any], *, user_id: str = DEFAULT_USER_ID
) -> dict[str, Any]:
    script_file = payload.get("script_file")
    if not script_file:
        raise ValueError("script_file is required for video task")

    prompt = payload.get("prompt")

    def _load():
        _manager = get_project_manager()
        _project = _manager.load_project(project_name)
        _project_path = _manager.get_project_path(project_name)
        _effective_prompt = prompt
        if not _effective_prompt:
            _script = _manager.load_script(project_name, script_file)
            _target_item, _, _, _, _, _ = _resolve_storyboard_item(_script, resource_id)
            _effective_prompt = _require_item_prompt(prompt, _target_item, "video_prompt", resource_id)
        return _project, _project_path, _effective_prompt

    project, project_path, effective_prompt = await asyncio.to_thread(_load)
    generator = await get_media_generator(project_name, payload=payload, user_id=user_id)

    storyboard_file = project_path / "storyboards" / f"scene_{resource_id}.png"
    if not storyboard_file.exists():
        raise ValueError(f"storyboard not found: scene_{resource_id}.png")

    prompt_text = _normalize_video_prompt(effective_prompt)
    aspect_ratio = get_aspect_ratio(project, "videos")
    seed = payload.get("seed")

    # 解析 provider / model，供 duration fallback 和解析度查詢共用
    provider_settings = payload.get("video_provider_settings", {})
    model_name = provider_settings.get("model")
    # payload 中 video_provider 由任務入隊時設定；project 中存的是 video_backend（"provider/model" 格式）
    provider_name = payload.get("video_provider")
    registry_provider_id = provider_name  # 用於 PROVIDER_REGISTRY 查詢的原始 provider_id
    if not provider_name:
        video_backend = project.get("video_backend") or ""
        if "/" in video_backend:
            provider_name, model_name = video_backend.split("/", 1)
            registry_provider_id = provider_name
    if not provider_name:
        from lib.config.resolver import ConfigResolver
        from lib.db import async_session_factory

        _resolver = ConfigResolver(async_session_factory)
        try:
            default_provider_id, default_model_id = await _resolver.default_video_backend()
        except Exception:
            default_provider_id, default_model_id = "gemini-aistudio", "veo-3.1-lite-generate-preview"
        registry_provider_id = default_provider_id
        model_name = model_name or default_model_id
        provider_name = _PROVIDER_ID_TO_BACKEND.get(default_provider_id, default_provider_id)
    # 將新 provider_id 對映為舊名稱以查詢解析度
    resolution_key = _PROVIDER_ID_TO_BACKEND.get(provider_name, provider_name)
    video_model_settings = project.get("video_model_settings", {})
    model_settings = video_model_settings.get(model_name, {}) if model_name else {}
    # 優先序：scene 覆蓋 (payload.video_resolution) > 專案級 model_settings > provider 預設
    resolution = (
        payload.get("video_resolution")
        or model_settings.get("resolution")
        or DEFAULT_VIDEO_RESOLUTION.get(resolution_key, "1080p")
    )

    # duration fallback: payload > project.default_duration > supported_durations[0] > 4
    duration_seconds = payload.get("duration_seconds") or project.get("default_duration")
    if not duration_seconds:
        duration_seconds = _get_model_default_duration(registry_provider_id, model_name)

    _, version, _, video_uri = await generator.generate_video_async(
        prompt=prompt_text,
        resource_type="videos",
        resource_id=resource_id,
        start_image=storyboard_file,
        aspect_ratio=aspect_ratio,
        duration_seconds=duration_seconds,
        resolution=resolution,
        seed=seed,
    )

    def _update_video_metadata():
        get_project_manager().update_scene_asset(
            project_name=project_name,
            script_filename=script_file,
            scene_id=resource_id,
            asset_type="video_clip",
            asset_path=f"videos/scene_{resource_id}.mp4",
        )
        if video_uri:
            get_project_manager().update_scene_asset(
                project_name=project_name,
                script_filename=script_file,
                scene_id=resource_id,
                asset_type="video_uri",
                asset_path=video_uri,
            )

    await asyncio.to_thread(_update_video_metadata)

    # 提取影片首幀作為縮圖
    video_file = project_path / f"videos/scene_{resource_id}.mp4"
    thumbnail_file = project_path / f"thumbnails/scene_{resource_id}.jpg"
    if await extract_video_thumbnail(video_file, thumbnail_file):
        await asyncio.to_thread(
            get_project_manager().update_scene_asset,
            project_name=project_name,
            script_filename=script_file,
            scene_id=resource_id,
            asset_type="video_thumbnail",
            asset_path=f"thumbnails/scene_{resource_id}.jpg",
        )
    else:
        thumbnail_file.unlink(missing_ok=True)

    latest_version = await asyncio.to_thread(
        lambda: generator.versions.get_versions("videos", resource_id)["versions"][-1]
    )

    result = {
        "version": version,
        "file_path": f"videos/scene_{resource_id}.mp4",
        "created_at": latest_version["created_at"],
        "resource_type": "videos",
        "resource_id": resource_id,
        "video_uri": video_uri,
    }
    if latest_version.get("adjusted"):
        result["adjusted"] = latest_version["adjusted"]
    return result


async def _finalize_generated_sheet(
    project_name: str,
    resource_type: str,
    resource_id: str,
    sheet_field: str,
    sheet_path: str,
    generator: MediaGenerator,
) -> str:
    def _finalize():
        def _set_sheet(project: dict) -> None:
            project[resource_type][resource_id][sheet_field] = sheet_path

        get_project_manager().update_project(project_name, _set_sheet)
        return generator.versions.get_versions(resource_type, resource_id)["versions"][-1]["created_at"]

    return await asyncio.to_thread(_finalize)


async def execute_character_task(
    project_name: str, resource_id: str, payload: dict[str, Any], *, user_id: str = DEFAULT_USER_ID
) -> dict[str, Any]:
    prompt = str(payload.get("prompt", "") or "").strip()
    if not prompt:
        prompt = resource_id

    def _prepare_char():
        _project = get_project_manager().load_project(project_name)
        _project_path = get_project_manager().get_project_path(project_name)
        if resource_id not in _project.get("characters", {}):
            raise ValueError(f"character not found: {resource_id}")
        _char_data = _project["characters"][resource_id]
        _style = _project.get("style", "")
        _style_desc = _project.get("style_description", "")
        _full_prompt = build_character_prompt(resource_id, prompt, _style, _style_desc)
        _ref_images = None
        _ref_path = _char_data.get("reference_image")
        if _ref_path:
            _full_ref = _project_path / _ref_path
            if _full_ref.exists():
                _ref_images = [_full_ref]
        return _project, _full_prompt, _ref_images

    project, full_prompt, reference_images = await asyncio.to_thread(_prepare_char)

    generator = await get_media_generator(project_name, payload=payload, user_id=user_id)
    aspect_ratio = get_aspect_ratio(project, "characters")

    _, version = await generator.generate_image_async(
        prompt=full_prompt,
        resource_type="characters",
        resource_id=resource_id,
        reference_images=reference_images,
        aspect_ratio=aspect_ratio,
        image_size="1K",
    )

    sheet_path = f"characters/{resource_id}.png"
    created_at = await _finalize_generated_sheet(
        project_name, "characters", resource_id, "character_sheet", sheet_path, generator
    )

    return {
        "version": version,
        "file_path": sheet_path,
        "created_at": created_at,
        "resource_type": "characters",
        "resource_id": resource_id,
    }


async def execute_clue_task(
    project_name: str, resource_id: str, payload: dict[str, Any], *, user_id: str = DEFAULT_USER_ID
) -> dict[str, Any]:
    prompt = str(payload.get("prompt", "") or "").strip()
    if not prompt:
        prompt = resource_id

    def _prepare_clue():
        _project = get_project_manager().load_project(project_name)
        if resource_id not in _project.get("clues", {}):
            raise ValueError(f"clue not found: {resource_id}")
        _style = _project.get("style", "")
        _style_desc = _project.get("style_description", "")
        _full_prompt = build_clue_prompt(resource_id, prompt, _style, _style_desc)
        return _project, _full_prompt

    project, full_prompt = await asyncio.to_thread(_prepare_clue)

    generator = await get_media_generator(project_name, payload=payload, user_id=user_id)
    aspect_ratio = get_aspect_ratio(project, "clues")

    _, version = await generator.generate_image_async(
        prompt=full_prompt,
        resource_type="clues",
        resource_id=resource_id,
        aspect_ratio=aspect_ratio,
        image_size="1K",
    )

    sheet_path = f"clues/{resource_id}.png"
    created_at = await _finalize_generated_sheet(
        project_name, "clues", resource_id, "clue_sheet", sheet_path, generator
    )

    return {
        "version": version,
        "file_path": sheet_path,
        "created_at": created_at,
        "resource_type": "clues",
        "resource_id": resource_id,
    }


async def execute_scene_task(
    project_name: str, resource_id: str, payload: dict[str, Any], *, user_id: str = DEFAULT_USER_ID
) -> dict[str, Any]:
    prompt = str(payload.get("prompt", "") or "").strip()
    if not prompt:
        prompt = resource_id

    def _prepare_scene():
        _project = get_project_manager().load_project(project_name)
        if resource_id not in _project.get("scenes", {}):
            raise ValueError(f"scene not found: {resource_id}")
        _style = _project.get("style", "")
        _style_desc = _project.get("style_description", "")
        _full_prompt = build_scene_prompt(resource_id, prompt, _style, _style_desc)
        return _project, _full_prompt

    project, full_prompt = await asyncio.to_thread(_prepare_scene)

    generator = await get_media_generator(project_name, payload=payload, user_id=user_id)
    aspect_ratio = get_aspect_ratio(project, "scenes")

    _, version = await generator.generate_image_async(
        prompt=full_prompt,
        resource_type="scenes",
        resource_id=resource_id,
        aspect_ratio=aspect_ratio,
        image_size="1K",
    )

    sheet_path = f"scenes/{resource_id}.png"
    created_at = await _finalize_generated_sheet(
        project_name, "scenes", resource_id, "scene_sheet", sheet_path, generator
    )

    return {
        "version": version,
        "file_path": sheet_path,
        "created_at": created_at,
        "resource_type": "scenes",
        "resource_id": resource_id,
    }


_TASK_EXECUTORS = {
    "storyboard": execute_storyboard_task,
    "video": execute_video_task,
    "character": execute_character_task,
    "clue": execute_clue_task,
    "scene": execute_scene_task,
}


async def execute_generation_task(task: dict[str, Any]) -> dict[str, Any]:
    task_type = task.get("task_type")
    project_name = task.get("project_name")
    resource_id = str(task.get("resource_id"))
    payload = task.get("payload") or {}
    user_id = task.get("user_id", DEFAULT_USER_ID)

    if not project_name:
        raise ValueError("task.project_name is required")

    executor = _TASK_EXECUTORS.get(task_type)
    if executor is None:
        raise ValueError(f"unsupported task_type: {task_type}")

    with project_change_source("worker"):
        result = await executor(project_name, resource_id, payload, user_id=user_id)
        _emit_generation_success_batch(
            task_type=task_type,
            project_name=project_name,
            resource_id=resource_id,
            payload=payload,
        )
        return result
