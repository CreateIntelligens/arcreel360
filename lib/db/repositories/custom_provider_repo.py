"""Custom provider repository."""

from __future__ import annotations

from sqlalchemy import delete, select

from lib.db.models.custom_provider import CustomProvider, CustomProviderModel
from lib.db.repositories.base import BaseRepository


class CustomProviderRepository(BaseRepository):
    """自定義供應商 + 模型 CRUD。"""

    @staticmethod
    def _normalize_api_format(api_format: str) -> str:
        if api_format not in {"openai", "google"}:
            raise ValueError(f"不支援的 api_format: {api_format}")
        return api_format

    @classmethod
    def _endpoint_for(cls, api_format: str, media_type: str) -> str:
        api_format = cls._normalize_api_format(api_format)
        endpoint_map = {
            ("openai", "text"): "openai-chat",
            ("openai", "image"): "openai-images",
            ("openai", "video"): "openai-video",
            ("google", "text"): "gemini-generate",
            ("google", "image"): "gemini-image",
            ("google", "video"): "openai-video",
        }
        try:
            return endpoint_map[(api_format, media_type)]
        except KeyError as exc:
            raise ValueError(f"不支援的 media_type: {media_type}") from exc

    def _model_payloads(self, api_format: str, models: list[dict]) -> list[dict]:
        payloads: list[dict] = []
        for model in models:
            payload = dict(model)
            media_type = payload["media_type"]
            payload["endpoint"] = self._endpoint_for(api_format, media_type)
            payloads.append(payload)
        return payloads

    # ── Provider CRUD ──────────────────────────────────────────────

    async def create_provider(
        self,
        display_name: str,
        api_format: str,
        base_url: str,
        api_key: str,
        models: list[dict] | None = None,
    ) -> CustomProvider:
        """建立供應商，可選同時建立模型列表。"""
        api_format = self._normalize_api_format(api_format)
        provider = CustomProvider(
            display_name=display_name,
            api_format=api_format,
            discovery_format=api_format,
            base_url=base_url,
            api_key=api_key,
        )
        self.session.add(provider)
        await self.session.flush()  # 獲取 provider.id

        if models:
            for m in self._model_payloads(api_format, models):
                model = CustomProviderModel(provider_id=provider.id, **m)
                self.session.add(model)
            await self.session.flush()

        return provider

    async def get_provider(self, provider_id: int) -> CustomProvider | None:
        stmt = select(CustomProvider).where(CustomProvider.id == provider_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_providers(self) -> list[CustomProvider]:
        stmt = select(CustomProvider).order_by(CustomProvider.id)
        result = await self.session.execute(stmt)
        return list(result.scalars())

    async def update_provider(self, provider_id: int, **kwargs) -> CustomProvider | None:
        """更新供應商欄位。返回更新後的物件，若不存在返回 None。"""
        provider = await self.get_provider(provider_id)
        if provider is None:
            return None
        if "api_format" in kwargs:
            normalized = self._normalize_api_format(kwargs["api_format"])
            kwargs["api_format"] = normalized
            kwargs["discovery_format"] = normalized
        for key, value in kwargs.items():
            setattr(provider, key, value)
        return provider

    async def delete_provider(self, provider_id: int) -> None:
        """刪除供應商及其所有模型。

        顯式刪除模型而非依賴 FK CASCADE，因為 SQLite 預設不啟用 foreign_keys pragma。
        """
        await self.session.execute(delete(CustomProviderModel).where(CustomProviderModel.provider_id == provider_id))
        await self.session.execute(delete(CustomProvider).where(CustomProvider.id == provider_id))
        await self.session.flush()

    # ── Model management ──────────────────────────────────────────

    async def list_models(self, provider_id: int) -> list[CustomProviderModel]:
        stmt = (
            select(CustomProviderModel)
            .where(CustomProviderModel.provider_id == provider_id)
            .order_by(CustomProviderModel.id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars())

    async def replace_models(self, provider_id: int, models: list[dict]) -> list[CustomProviderModel]:
        """刪除舊模型，插入新列表。返回新建立的模型。"""
        provider = await self.get_provider(provider_id)
        if provider is None:
            return []
        await self.session.execute(delete(CustomProviderModel).where(CustomProviderModel.provider_id == provider_id))
        new_models = []
        for m in self._model_payloads(provider.api_format, models):
            model = CustomProviderModel(provider_id=provider_id, **m)
            self.session.add(model)
            new_models.append(model)
        await self.session.flush()
        return new_models

    async def update_model(self, model_id: int, **kwargs) -> CustomProviderModel | None:
        """更新模型欄位。返回更新後的物件，若不存在返回 None。"""
        stmt = select(CustomProviderModel).where(CustomProviderModel.id == model_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        if "media_type" in kwargs:
            provider = await self.get_provider(model.provider_id)
            if provider is None:
                return None
            kwargs["endpoint"] = self._endpoint_for(provider.api_format, kwargs["media_type"])
        for key, value in kwargs.items():
            setattr(model, key, value)
        return model

    async def delete_model(self, model_id: int) -> None:
        """刪除單個模型。"""
        await self.session.execute(delete(CustomProviderModel).where(CustomProviderModel.id == model_id))
        await self.session.flush()

    async def list_all_enabled_models(self) -> list[CustomProviderModel]:
        """跨所有供應商獲取全部已啟用模型。"""
        stmt = (
            select(CustomProviderModel)
            .where(CustomProviderModel.is_enabled == True)  # noqa: E712
            .order_by(CustomProviderModel.provider_id, CustomProviderModel.id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars())

    async def list_providers_with_models(self) -> list[tuple[CustomProvider, list[CustomProviderModel]]]:
        """獲取所有供應商及其模型，僅 2 次查詢。"""
        providers = await self.list_providers()
        if not providers:
            return []
        provider_ids = [p.id for p in providers]
        stmt = (
            select(CustomProviderModel)
            .where(CustomProviderModel.provider_id.in_(provider_ids))
            .order_by(CustomProviderModel.provider_id, CustomProviderModel.id)
        )
        result = await self.session.execute(stmt)
        all_models = list(result.scalars())

        models_by_provider: dict[int, list[CustomProviderModel]] = {p.id: [] for p in providers}
        for m in all_models:
            models_by_provider.setdefault(m.provider_id, []).append(m)
        return [(p, models_by_provider.get(p.id, [])) for p in providers]

    async def list_enabled_models_by_media_type(self, media_type: str) -> list[CustomProviderModel]:
        """跨所有供應商獲取指定媒體型別的已啟用模型。"""
        stmt = (
            select(CustomProviderModel)
            .where(
                CustomProviderModel.media_type == media_type,
                CustomProviderModel.is_enabled == True,  # noqa: E712
            )
            .order_by(CustomProviderModel.id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars())

    async def get_model_by_ids(self, provider_id: int, model_id: str) -> CustomProviderModel | None:
        """根據供應商 ID 和模型 ID 獲取模型。"""
        stmt = select(CustomProviderModel).where(
            CustomProviderModel.provider_id == provider_id,
            CustomProviderModel.model_id == model_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_default_model(self, provider_id: int, media_type: str) -> CustomProviderModel | None:
        """獲取指定供應商 + 媒體型別的預設已啟用模型。"""
        stmt = select(CustomProviderModel).where(
            CustomProviderModel.provider_id == provider_id,
            CustomProviderModel.media_type == media_type,
            CustomProviderModel.is_default == True,  # noqa: E712
            CustomProviderModel.is_enabled == True,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
