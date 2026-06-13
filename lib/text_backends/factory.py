"""文字 backend 工廠。"""

from __future__ import annotations

from lib.config.resolver import ConfigResolver
from lib.custom_provider import is_custom_provider, parse_provider_id
from lib.db import async_session_factory
from lib.providers import PROVIDER_BYTEPLUS, PROVIDER_OPENAI, normalize_provider_id
from lib.text_backends.base import TextBackend, TextTaskType
from lib.text_backends.registry import create_backend

PROVIDER_ID_TO_BACKEND: dict[str, str] = {
    "gemini-aistudio": "gemini",
    "gemini-vertex": "gemini",
    "ark": PROVIDER_BYTEPLUS,
    "seedance": PROVIDER_BYTEPLUS,
    PROVIDER_BYTEPLUS: PROVIDER_BYTEPLUS,
    "grok": "grok",
    "openai": "openai",
}


async def _create_backend_instance(
    resolver_session,
    provider_id: str,
    model_id: str | None,
) -> TextBackend:
    # Custom providers use a separate factory path
    if is_custom_provider(provider_id):
        from sqlalchemy import select

        from lib.custom_provider.factory import create_custom_backend
        from lib.db.models.custom_provider import CustomProviderModel
        from lib.db.repositories.custom_provider_repo import CustomProviderRepository

        async with resolver_session._open_session() as (session, _):
            repo = CustomProviderRepository(session)
            db_id = parse_provider_id(provider_id)
            provider = await repo.get_provider(db_id)
            if provider is None:
                raise ValueError("配置的自定義供應商已被刪除，請到專案設定中重新選擇文字模型")
            name = provider.display_name
            # 校驗 model_id 仍存在且已啟用，否則回退預設模型
            if model_id:
                stmt = select(CustomProviderModel).where(
                    CustomProviderModel.provider_id == db_id,
                    CustomProviderModel.model_id == model_id,
                    CustomProviderModel.media_type == "text",
                    CustomProviderModel.is_enabled == True,  # noqa: E712
                )
                result = await session.execute(stmt)
                if result.scalar_one_or_none() is None:
                    model_id = None
            if not model_id:
                default_model = await repo.get_default_model(db_id, "text")
                if default_model:
                    model_id = default_model.model_id
                else:
                    raise ValueError(f"供應商「{name}」沒有可用的文字模型，請到專案設定中重新選擇")
            return create_custom_backend(provider=provider, model_id=model_id, media_type="text")

    provider_config = await resolver_session.provider_config(provider_id)

    backend_name = PROVIDER_ID_TO_BACKEND.get(provider_id, provider_id)
    kwargs: dict = {"model": model_id}

    if provider_id == "gemini-vertex":
        kwargs["backend"] = "vertex"
        kwargs["gcs_bucket"] = provider_config.get("gcs_bucket")
    else:
        kwargs["api_key"] = provider_config.get("api_key")
        if provider_id in ("gemini-aistudio", PROVIDER_OPENAI):
            kwargs["base_url"] = provider_config.get("base_url")

    return create_backend(backend_name, **kwargs)


async def create_text_backend_for_task(
    task_type: TextTaskType,
    project_name: str | None = None,
) -> TextBackend:
    """從 DB 配置建立文字 backend。"""
    resolver = ConfigResolver(async_session_factory)

    async with resolver.session() as r:
        provider_id, model_id = await r.text_backend_for_task(task_type, project_name)
        provider_id = normalize_provider_id(provider_id)
        return await _create_backend_instance(r, provider_id, model_id)


async def create_text_backend_by_model_str(
    model_str: str,
) -> TextBackend:
    """根據 provider/model 格式的字串建立文字 backend。"""
    if "/" not in model_str:
        raise ValueError(f"無效的文字模型格式: {model_str}，應為 provider/model 格式")
    provider_id, model_id = model_str.split("/", 1)
    provider_id = normalize_provider_id(provider_id)

    resolver = ConfigResolver(async_session_factory)
    async with resolver.session() as r:
        return await _create_backend_instance(r, provider_id, model_id)
