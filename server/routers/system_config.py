"""
System configuration APIs.

Handles non-provider global settings: default backends, audio, anthropic config.
Provider-specific configuration (API keys, rate limits, credentials, connection test)
is managed by the providers router.
"""

from __future__ import annotations

import logging
import re
from typing import Annotated, Any, TypedDict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from lib.config.registry import PROVIDER_REGISTRY
from lib.config.repository import mask_secret
from lib.config.service import (
    ConfigService,
    sync_anthropic_env,
)
from lib.db import get_async_session
from server.auth import CurrentUser
from server.dependencies import get_config_service
from server.routers._validators import validate_backend_value

logger = logging.getLogger(__name__)

router = APIRouter()

_ASSISTANT_PROVIDERS = ("claude", "gemini-lite", "gemini-full", "openai-lite", "openai-full")
_BYTEPLUS_VIDEO_ENDPOINT_SETTING = "byteplus_video_endpoint_id"
_BYTEPLUS_VIDEO_ENDPOINT_RE = re.compile(r"^ep-[A-Za-z0-9-]+$")


def _normalize_assistant_provider(value: str) -> str:
    return value.strip().replace("_", "-")


def _compact_endpoint_id(value: str | None) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def _normalize_byteplus_video_endpoint_id(value: str | None) -> str:
    endpoint_id = _compact_endpoint_id(value)
    if endpoint_id and not _BYTEPLUS_VIDEO_ENDPOINT_RE.fullmatch(endpoint_id):
        raise HTTPException(
            status_code=422,
            detail=f"{_BYTEPLUS_VIDEO_ENDPOINT_SETTING} 必須是 ep- 開頭的 ModelArk Endpoint ID",
        )
    return endpoint_id


async def _resolve_byteplus_video_endpoint_id(
    svc: ConfigService,
    all_settings: dict[str, str] | None,
) -> str:
    if all_settings is not None:
        return _compact_endpoint_id(all_settings.get(_BYTEPLUS_VIDEO_ENDPOINT_SETTING, ""))
    return _compact_endpoint_id(await svc.get_setting(_BYTEPLUS_VIDEO_ENDPOINT_SETTING, ""))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _OptionsDict(TypedDict):
    video_backends: list[str]
    image_backends: list[str]
    text_backends: list[str]
    assistant_providers: list[str]
    provider_names: dict[str, str]


async def _build_options(
    svc: ConfigService,
    session: AsyncSession,
    all_settings: dict[str, str] | None = None,
) -> _OptionsDict:
    """Compute available backends from ready providers."""
    statuses = await svc.get_all_providers_status()
    ready_providers = {s.name for s in statuses if s.status == "ready"}

    buckets: dict[str, list[str]] = {
        "video_backends": [],
        "image_backends": [],
        "text_backends": [],
    }
    provider_names: dict[str, str] = {}
    _MEDIA_TO_BUCKET = {"video": "video_backends", "image": "image_backends", "text": "text_backends"}

    for provider_id, meta in PROVIDER_REGISTRY.items():
        if provider_id not in ready_providers:
            continue
        for model_id, model_info in meta.models.items():
            bucket = _MEDIA_TO_BUCKET.get(model_info.media_type)
            if bucket:
                buckets[bucket].append(f"{provider_id}/{model_id}")

    from lib.custom_provider import make_provider_id
    from lib.db.repositories.custom_provider_repo import CustomProviderRepository

    try:
        repo = CustomProviderRepository(session)
        providers = await repo.list_providers()
        provider_name_map = {p.id: p.display_name for p in providers}
        enabled_models = await repo.list_all_enabled_models()
        for model in enabled_models:
            pid = make_provider_id(model.provider_id)
            bucket = _MEDIA_TO_BUCKET.get(model.media_type)
            if bucket:
                buckets[bucket].append(f"{pid}/{model.model_id}")
            if pid not in provider_names and model.provider_id in provider_name_map:
                provider_names[pid] = provider_name_map[model.provider_id]
    except Exception:
        pass  # Non-fatal: custom providers unavailable shouldn't break the options endpoint

    return {**buckets, "assistant_providers": list(_ASSISTANT_PROVIDERS), "provider_names": provider_names}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class SystemConfigPatchRequest(BaseModel):
    assistant_provider: str | None = None
    default_video_backend: str | None = None
    default_image_backend: str | None = None
    default_text_backend: str | None = None
    byteplus_video_endpoint_id: str | None = None
    video_generate_audio: bool | None = None
    anthropic_api_key: str | None = None
    anthropic_base_url: str | None = None
    anthropic_model: str | None = None
    anthropic_default_haiku_model: str | None = None
    anthropic_default_opus_model: str | None = None
    anthropic_default_sonnet_model: str | None = None
    claude_code_subagent_model: str | None = None
    agent_session_cleanup_delay_seconds: int | None = None
    agent_max_concurrent_sessions: int | None = None
    text_backend_script: str | None = None
    text_backend_overview: str | None = None
    text_backend_style: str | None = None


# Setting keys that map directly to string DB settings
_STRING_SETTINGS = (
    "assistant_provider",
    "anthropic_base_url",
    "anthropic_model",
    "anthropic_default_haiku_model",
    "anthropic_default_opus_model",
    "anthropic_default_sonnet_model",
    "claude_code_subagent_model",
    "text_backend_script",
    "text_backend_overview",
    "text_backend_style",
)


# ---------------------------------------------------------------------------
# GET /system/config
# ---------------------------------------------------------------------------


@router.get("/system/config")
async def get_system_config(
    _user: CurrentUser,
    svc: Annotated[ConfigService, Depends(get_config_service)],
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    # Read all settings in a single query
    all_s = await svc.get_all_settings()
    video_generate_audio_raw = all_s.get("video_generate_audio", "false")
    video_generate_audio = video_generate_audio_raw.lower() in ("true", "1", "yes")
    anthropic_key = all_s.get("anthropic_api_key", "")
    byteplus_video_endpoint_id = _compact_endpoint_id(all_s.get(_BYTEPLUS_VIDEO_ENDPOINT_SETTING, ""))

    settings: dict[str, Any] = {
        "assistant_provider": all_s.get("assistant_provider") or "claude",
        "default_video_backend": all_s.get("default_video_backend", ""),
        "default_image_backend": all_s.get("default_image_backend", ""),
        "default_text_backend": all_s.get("default_text_backend", ""),
        "byteplus_video_endpoint_id": byteplus_video_endpoint_id,
        "video_generate_audio": video_generate_audio,
        "anthropic_api_key": {
            "is_set": bool(anthropic_key),
            "masked": mask_secret(anthropic_key) if anthropic_key else None,
        },
        "anthropic_base_url": all_s.get("anthropic_base_url") or None,
        "anthropic_model": all_s.get("anthropic_model") or None,
        "anthropic_default_haiku_model": all_s.get("anthropic_default_haiku_model") or None,
        "anthropic_default_opus_model": all_s.get("anthropic_default_opus_model") or None,
        "anthropic_default_sonnet_model": all_s.get("anthropic_default_sonnet_model") or None,
        "claude_code_subagent_model": all_s.get("claude_code_subagent_model") or None,
        "agent_session_cleanup_delay_seconds": int(all_s.get("agent_session_cleanup_delay_seconds") or "300"),
        "agent_max_concurrent_sessions": int(all_s.get("agent_max_concurrent_sessions") or "5"),
        "text_backend_script": all_s.get("text_backend_script") or "",
        "text_backend_overview": all_s.get("text_backend_overview") or "",
        "text_backend_style": all_s.get("text_backend_style") or "",
    }

    options = await _build_options(svc, session, all_s)

    return {"settings": settings, "options": options}


# ---------------------------------------------------------------------------
# PATCH /system/config
# ---------------------------------------------------------------------------


@router.patch("/system/config")
async def patch_system_config(
    req: SystemConfigPatchRequest,
    _user: CurrentUser,
    svc: Annotated[ConfigService, Depends(get_config_service)],
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    for field_name in req.model_fields_set:
        patch[field_name] = getattr(req, field_name)

    # Validate backend references (empty string = auto-resolve)
    for backend_key in ("default_video_backend", "default_image_backend", "default_text_backend"):
        if backend_key in patch:
            value = str(patch[backend_key] or "").strip()
            if value:
                validate_backend_value(value, backend_key)
            await svc.set_setting(backend_key, value)

    if "assistant_provider" in patch:
        value = _normalize_assistant_provider(str(patch["assistant_provider"] or "")) or "claude"
        if value not in _ASSISTANT_PROVIDERS:
            raise HTTPException(
                status_code=422, detail=f"assistant_provider 必須是 {', '.join(_ASSISTANT_PROVIDERS)} 之一"
            )
        await svc.set_setting("assistant_provider", value)

    # Boolean settings
    if "video_generate_audio" in patch and patch["video_generate_audio"] is not None:
        await svc.set_setting("video_generate_audio", "true" if patch["video_generate_audio"] else "false")

    if _BYTEPLUS_VIDEO_ENDPOINT_SETTING in patch:
        endpoint_id = _normalize_byteplus_video_endpoint_id(patch[_BYTEPLUS_VIDEO_ENDPOINT_SETTING])
        await svc.set_setting(_BYTEPLUS_VIDEO_ENDPOINT_SETTING, endpoint_id)

    # Anthropic API key (secret)
    if "anthropic_api_key" in patch:
        value = patch["anthropic_api_key"]
        if value:
            await svc.set_setting("anthropic_api_key", str(value).strip())
        else:
            await svc.set_setting("anthropic_api_key", "")

    # Integer settings with range validation
    _INT_SETTINGS_RANGES = {
        "agent_session_cleanup_delay_seconds": (10, 3600),
        "agent_max_concurrent_sessions": (1, 20),
    }
    for key, (min_val, max_val) in _INT_SETTINGS_RANGES.items():
        if key in patch and patch[key] is not None:
            value = int(patch[key])
            if not (min_val <= value <= max_val):
                raise HTTPException(
                    status_code=422,
                    detail=f"{key} 應在 {min_val}-{max_val} 之間",
                )
            await svc.set_setting(key, str(value))

    # String settings
    for key in _STRING_SETTINGS:
        if key in patch:
            if key == "assistant_provider":
                continue
            value = patch[key]
            await svc.set_setting(key, str(value).strip() if value else "")

    await session.commit()

    # Sync Anthropic settings to env vars so Claude Agent SDK picks them up
    all_settings = await svc.get_all_settings()
    sync_anthropic_env(all_settings)

    # Return updated config
    return await get_system_config(_user=_user, svc=svc)
