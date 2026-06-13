"""Test ProviderMeta with ModelInfo structure."""

from lib.config.registry import PROVIDER_REGISTRY, ModelInfo, ProviderMeta


class TestModelInfo:
    def test_basic(self):
        m = ModelInfo(
            display_name="Test Model",
            media_type="text",
            capabilities=["text_generation"],
            default=True,
        )
        assert m.display_name == "Test Model"
        assert m.media_type == "text"
        assert m.default is True


class TestProviderMeta:
    def test_media_types_derived_from_models(self):
        meta = ProviderMeta(
            display_name="Test",
            description="Test provider",
            required_keys=["api_key"],
            models={
                "text-model": ModelInfo("TM", "text", ["text_generation"], default=True),
                "image-model": ModelInfo("IM", "image", ["text_to_image"], default=True),
            },
        )
        assert sorted(meta.media_types) == ["image", "text"]

    def test_capabilities_derived_from_models(self):
        meta = ProviderMeta(
            display_name="Test",
            description="Test provider",
            required_keys=["api_key"],
            models={
                "m1": ModelInfo("M1", "text", ["text_generation", "vision"]),
                "m2": ModelInfo("M2", "image", ["text_to_image"]),
            },
        )
        assert sorted(meta.capabilities) == ["text_generation", "text_to_image", "vision"]

    def test_empty_models(self):
        meta = ProviderMeta(
            display_name="T",
            description="T",
            required_keys=[],
        )
        assert meta.media_types == []
        assert meta.capabilities == []


class TestProviderRegistry:
    def test_all_providers_have_text_models(self):
        # ai360 是純影片供應商，無文字模型
        for provider_id in ("gemini-aistudio", "gemini-vertex", "byteplus", "grok", "openai"):
            meta = PROVIDER_REGISTRY[provider_id]
            text_models = [mid for mid, m in meta.models.items() if m.media_type == "text"]
            assert len(text_models) > 0, f"{provider_id} has no text models"

    def test_all_providers_have_image_models(self):
        for provider_id in ("gemini-aistudio", "gemini-vertex", "grok", "openai"):
            meta = PROVIDER_REGISTRY[provider_id]
            image_models = [mid for mid, m in meta.models.items() if m.media_type == "image"]
            assert len(image_models) > 0, f"{provider_id} has no image models"

    def test_all_providers_have_video_models(self):
        for provider_id in ("gemini-aistudio", "gemini-vertex", "byteplus", "grok"):
            meta = PROVIDER_REGISTRY[provider_id]
            video_models = [mid for mid, m in meta.models.items() if m.media_type == "video"]
            assert len(video_models) > 0, f"{provider_id} has no video models"

    def test_each_media_type_has_default(self):
        for provider_id, meta in PROVIDER_REGISTRY.items():
            by_type: dict[str, list[ModelInfo]] = {}
            for m in meta.models.values():
                by_type.setdefault(m.media_type, []).append(m)
            for mt, models in by_type.items():
                defaults = [m for m in models if m.default]
                assert len(defaults) == 1, f"{provider_id} has {len(defaults)} default {mt} models, expected 1"

    def test_media_types_property_includes_text(self):
        # ai360 是純影片供應商，無文字 media type
        for provider_id in ("gemini-aistudio", "gemini-vertex", "byteplus", "grok", "openai"):
            meta = PROVIDER_REGISTRY[provider_id]
            assert "text" in meta.media_types, f"{provider_id} missing 'text'"

    def test_byteplus_video_models_only_include_seedance_2(self):
        assert "ark" not in PROVIDER_REGISTRY
        meta = PROVIDER_REGISTRY["byteplus"]
        video_models = {mid: m for mid, m in meta.models.items() if m.media_type == "video"}
        assert set(video_models) == {"doubao-seedance-2-0-260128"}
        caps = video_models["doubao-seedance-2-0-260128"].capabilities
        assert "video_extend" in caps
        assert "flex_tier" not in caps
        assert video_models["doubao-seedance-2-0-260128"].default is True

    def test_byteplus_has_no_seedream_image_models(self):
        meta = PROVIDER_REGISTRY["byteplus"]
        image_models = {mid: m for mid, m in meta.models.items() if m.media_type == "image"}
        assert image_models == {}
        assert not any("seedream" in mid for mid in meta.models)

    def test_openai_image_models_only_include_gpt_image_2_series(self):
        meta = PROVIDER_REGISTRY["openai"]
        image_models = {mid: m for mid, m in meta.models.items() if m.media_type == "image"}
        assert set(image_models) == {"gpt-image-2", "gpt-image-2-2026-04-21"}
        assert image_models["gpt-image-2"].default is True
        assert image_models["gpt-image-2-2026-04-21"].default is False
