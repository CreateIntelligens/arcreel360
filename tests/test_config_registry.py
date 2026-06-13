from lib.config.registry import PROVIDER_REGISTRY, ModelInfo, ProviderMeta


def test_all_providers_registered():
    assert set(PROVIDER_REGISTRY.keys()) == {"gemini-aistudio", "gemini-vertex", "byteplus", "grok", "openai", "ai360"}


def test_provider_meta_fields():
    meta = PROVIDER_REGISTRY["gemini-aistudio"]
    assert isinstance(meta, ProviderMeta)
    assert meta.display_name == "AI Studio"
    assert "video" in meta.media_types
    assert "image" in meta.media_types
    assert "api_key" in meta.required_keys
    assert "api_key" in meta.secret_keys
    assert "text_to_video" in meta.capabilities


def test_byteplus_supports_text_and_video_only():
    meta = PROVIDER_REGISTRY["byteplus"]
    assert "video" in meta.media_types
    assert "text" in meta.media_types
    assert "image" not in meta.media_types
    assert meta.display_name == "BytePlus ModelArk"


def test_required_keys_are_subset_of_all_keys():
    for name, meta in PROVIDER_REGISTRY.items():
        all_keys = set(meta.required_keys) | set(meta.optional_keys)
        for rk in meta.required_keys:
            assert rk in all_keys, f"{name}: required key {rk} not in all keys"


def test_secret_keys_are_subset_of_required_or_optional():
    for name, meta in PROVIDER_REGISTRY.items():
        all_keys = set(meta.required_keys) | set(meta.optional_keys)
        for sk in meta.secret_keys:
            assert sk in all_keys, f"{name}: secret key {sk} not in all keys"


class TestModelInfoDurations:
    def test_video_models_have_supported_durations(self):
        """所有預置影片模型必須宣告 supported_durations。"""
        for provider_id, meta in PROVIDER_REGISTRY.items():
            for model_id, model_info in meta.models.items():
                if model_info.media_type == "video":
                    assert len(model_info.supported_durations) > 0, (
                        f"{provider_id}/{model_id} 是影片模型但未宣告 supported_durations"
                    )

    def test_non_video_models_have_empty_durations(self):
        """非影片模型的 supported_durations 應為空列表。"""
        for provider_id, meta in PROVIDER_REGISTRY.items():
            for model_id, model_info in meta.models.items():
                if model_info.media_type != "video":
                    assert model_info.supported_durations == [], (
                        f"{provider_id}/{model_id} 不是影片模型但有 supported_durations"
                    )

    def test_aistudio_veo_has_resolution_constraints(self):
        """AI Studio Veo 模型在 1080p 下只支援 8s。"""
        meta = PROVIDER_REGISTRY["gemini-aistudio"]
        for _model_id, model_info in meta.models.items():
            if model_info.media_type == "video":
                assert "1080p" in model_info.duration_resolution_constraints
                assert model_info.duration_resolution_constraints["1080p"] == [8]

    def test_vertex_veo_has_resolution_constraints(self):
        """Vertex Veo 模型在 1080p / 4k 下強制 8 秒，與 AI Studio 規則一致。"""
        meta = PROVIDER_REGISTRY["gemini-vertex"]
        for _model_id, model_info in meta.models.items():
            if model_info.media_type == "video":
                assert model_info.duration_resolution_constraints.get("1080p") == [8]
                assert model_info.duration_resolution_constraints.get("4k") == [8]
                assert model_info.reference_image_force_duration == 8

    def test_model_info_default_values(self):
        """ModelInfo 新欄位的預設值。"""
        mi = ModelInfo(display_name="test", media_type="text", capabilities=[])
        assert mi.supported_durations == []
        assert mi.duration_resolution_constraints == {}
