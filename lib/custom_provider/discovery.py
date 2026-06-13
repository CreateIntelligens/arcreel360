"""自定義供應商模型發現。

提供模型列表查詢與 media_type 推斷功能。
"""

from __future__ import annotations

import asyncio
import logging
import re

from google import genai
from openai import OpenAI

logger = logging.getLogger(__name__)

_IMAGE_PATTERN = re.compile(r"image|dall|img", re.IGNORECASE)
_VIDEO_PATTERN = re.compile(r"video|sora|kling|wan|seedance|cog|mochi|veo|pika", re.IGNORECASE)

# Google generation method → media_type 對映
_GENERATION_METHOD_MAP: dict[str, str] = {
    "generateVideo": "video",
    "generateVideos": "video",
    "generateImages": "image",
    "generateImage": "image",
}


def infer_media_type(model_id: str) -> str:
    """根據模型 ID 關鍵字推斷 media_type。

    Returns:
        "image" | "video" | "text"
    """
    if _IMAGE_PATTERN.search(model_id):
        return "image"
    if _VIDEO_PATTERN.search(model_id):
        return "video"
    return "text"


async def discover_models(api_format: str, base_url: str | None, api_key: str) -> list[dict]:
    """查詢供應商的可用模型列表。

    Args:
        api_format: API 格式 ("openai" | "google")
        base_url: 供應商 API 基礎 URL
        api_key: API 金鑰

    Returns:
        模型列表，每項包含: model_id, display_name, media_type, is_default, is_enabled

    Raises:
        ValueError: api_format 不支援
    """
    if api_format == "openai":
        return await _discover_openai(base_url, api_key)
    elif api_format == "google":
        return await _discover_google(base_url, api_key)
    else:
        raise ValueError(f"不支援的 api_format: {api_format!r}，支援: 'openai', 'google'")


async def _discover_openai(base_url: str | None, api_key: str) -> list[dict]:
    """透過 OpenAI 相容 API 發現模型。"""

    def _sync():
        from lib.config.url_utils import ensure_openai_base_url

        client = OpenAI(api_key=api_key, base_url=ensure_openai_base_url(base_url))
        raw_models = client.models.list()
        models = sorted(raw_models, key=lambda m: m.id)
        return _build_result_list([(m.id, infer_media_type(m.id)) for m in models])

    return await asyncio.to_thread(_sync)


async def _discover_google(base_url: str | None, api_key: str) -> list[dict]:
    """透過 Google genai SDK 發現模型。"""

    def _sync():
        from lib.config.url_utils import ensure_google_base_url

        kwargs: dict = {"api_key": api_key}
        effective_url = ensure_google_base_url(base_url) if base_url else None
        if effective_url:
            kwargs["http_options"] = {"base_url": effective_url}
        client = genai.Client(**kwargs)

        raw_models = client.models.list()

        entries: list[tuple[str, str]] = []
        for m in raw_models:
            model_id = m.name
            if model_id.startswith("models/"):
                model_id = model_id[len("models/") :]
            media_type = _infer_from_generation_methods(m) or infer_media_type(model_id)
            entries.append((model_id, media_type))

        entries.sort(key=lambda e: e[0])
        return _build_result_list(entries)

    return await asyncio.to_thread(_sync)


def _infer_from_generation_methods(model) -> str | None:
    """從 Google model 的 supported_generation_methods 推斷 media_type。

    Returns:
        推斷出的 media_type，無法推斷時返回 None
    """
    methods = getattr(model, "supported_generation_methods", None)
    if not methods:
        return None

    for method in methods:
        if method in _GENERATION_METHOD_MAP:
            return _GENERATION_METHOD_MAP[method]

    return None


def _build_result_list(entries: list[tuple[str, str]]) -> list[dict]:
    """將 (model_id, media_type) 列表轉為結果字典列表，標記每種 media_type 的第一個為 default。"""
    seen_types: set[str] = set()
    result: list[dict] = []

    for model_id, media_type in entries:
        is_default = media_type not in seen_types
        seen_types.add(media_type)
        result.append(
            {
                "model_id": model_id,
                "display_name": model_id,
                "media_type": media_type,
                "is_default": is_default,
                "is_enabled": True,
            }
        )

    return result
