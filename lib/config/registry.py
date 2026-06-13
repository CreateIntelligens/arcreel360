from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelInfo:
    display_name: str
    media_type: str
    capabilities: list[str]
    default: bool = False
    supported_durations: list[int] = field(default_factory=list)
    duration_resolution_constraints: dict[str, list[int]] = field(default_factory=dict)
    supported_resolutions: list[str] = field(default_factory=list)
    reference_image_force_duration: int | None = None
    # 圖片模型支援的解析度尺寸，僅對 media_type == "image" 有意義；空清單 = 沿用現狀
    supported_image_sizes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProviderMeta:
    display_name: str
    description: str
    required_keys: list[str]
    optional_keys: list[str] = field(default_factory=list)
    secret_keys: list[str] = field(default_factory=list)
    models: dict[str, ModelInfo] = field(default_factory=dict)

    @property
    def media_types(self) -> list[str]:
        return sorted(set(m.media_type for m in self.models.values()))

    @property
    def capabilities(self) -> list[str]:
        return sorted(set(c for m in self.models.values() for c in m.capabilities))


PROVIDER_REGISTRY: dict[str, ProviderMeta] = {
    "gemini-aistudio": ProviderMeta(
        display_name="AI Studio",
        description="Google AI Studio 提供 Gemini 系列模型，支援圖片和影片生成，適合快速原型和個人專案。",
        required_keys=["api_key"],
        optional_keys=["base_url", "image_rpm", "video_rpm", "request_gap", "image_max_workers", "video_max_workers"],
        secret_keys=["api_key"],
        models={
            # --- text ---
            "gemini-3.1-pro-preview": ModelInfo(
                display_name="Gemini 3.1 Pro",
                media_type="text",
                capabilities=["text_generation", "structured_output", "vision"],
            ),
            "gemini-3.1-flash-lite": ModelInfo(
                display_name="Gemini 3.1 Flash Lite",
                media_type="text",
                capabilities=["text_generation", "structured_output", "vision"],
                default=True,
            ),
            # --- image ---
            "gemini-3-pro-image-preview": ModelInfo(
                display_name="Gemini 3 Pro Image",
                media_type="image",
                supported_image_sizes=["1K", "2K", "4K"],
                capabilities=["text_to_image", "image_to_image"],
            ),
            "gemini-3.1-flash-image-preview": ModelInfo(
                display_name="Gemini 3.1 Flash Image",
                media_type="image",
                supported_image_sizes=["512PX", "1K", "2K", "4K"],
                capabilities=["text_to_image", "image_to_image"],
                default=True,
            ),
            # --- video ---
            "veo-3.1-generate-preview": ModelInfo(
                display_name="Veo 3.1",
                media_type="video",
                capabilities=["text_to_video", "image_to_video", "negative_prompt", "video_extend"],
                supported_durations=[4, 6, 8],
                supported_resolutions=["720p", "1080p", "4k"],
                duration_resolution_constraints={"1080p": [8], "4k": [8]},
                reference_image_force_duration=8,
            ),
            "veo-3.1-fast-generate-preview": ModelInfo(
                display_name="Veo 3.1 Fast",
                media_type="video",
                capabilities=["text_to_video", "image_to_video", "negative_prompt", "video_extend"],
                supported_durations=[4, 6, 8],
                supported_resolutions=["720p", "1080p", "4k"],
                duration_resolution_constraints={"1080p": [8], "4k": [8]},
                reference_image_force_duration=8,
            ),
            "veo-3.1-lite-generate-preview": ModelInfo(
                display_name="Veo 3.1 Lite",
                media_type="video",
                capabilities=["text_to_video", "image_to_video", "video_extend"],
                default=True,
                supported_durations=[4, 6, 8],
                supported_resolutions=["720p", "1080p"],
                duration_resolution_constraints={"1080p": [8]},
                reference_image_force_duration=8,
            ),
        },
    ),
    "gemini-vertex": ProviderMeta(
        display_name="Vertex AI",
        description="Google Cloud Vertex AI 企業級平臺，支援 Gemini 和 Imagen 模型，提供更高配額和音訊生成能力。",
        required_keys=["credentials_path"],
        optional_keys=["gcs_bucket", "image_rpm", "video_rpm", "request_gap", "image_max_workers", "video_max_workers"],
        secret_keys=[],
        models={
            # --- text ---
            "gemini-3.1-pro-preview": ModelInfo(
                display_name="Gemini 3.1 Pro",
                media_type="text",
                capabilities=["text_generation", "structured_output", "vision"],
            ),
            "gemini-3.1-flash-lite": ModelInfo(
                display_name="Gemini 3.1 Flash Lite",
                media_type="text",
                capabilities=["text_generation", "structured_output", "vision"],
                default=True,
            ),
            # --- image ---
            "gemini-3-pro-image-preview": ModelInfo(
                display_name="Gemini 3 Pro Image",
                media_type="image",
                supported_image_sizes=["1K", "2K", "4K"],
                capabilities=["text_to_image", "image_to_image"],
            ),
            "gemini-3.1-flash-image-preview": ModelInfo(
                display_name="Gemini 3.1 Flash Image",
                media_type="image",
                supported_image_sizes=["512PX", "1K", "2K", "4K"],
                capabilities=["text_to_image", "image_to_image"],
                default=True,
            ),
            # --- video ---
            "veo-3.1-generate-001": ModelInfo(
                display_name="Veo 3.1",
                media_type="video",
                capabilities=["text_to_video", "image_to_video", "generate_audio", "negative_prompt", "video_extend"],
                supported_durations=[4, 6, 8],
                supported_resolutions=["720p", "1080p", "4k"],
                duration_resolution_constraints={"1080p": [8], "4k": [8]},
                reference_image_force_duration=8,
            ),
            "veo-3.1-fast-generate-001": ModelInfo(
                display_name="Veo 3.1 Fast",
                media_type="video",
                capabilities=["text_to_video", "image_to_video", "generate_audio", "negative_prompt", "video_extend"],
                default=True,
                supported_durations=[4, 6, 8],
                supported_resolutions=["720p", "1080p", "4k"],
                duration_resolution_constraints={"1080p": [8], "4k": [8]},
                reference_image_force_duration=8,
            ),
        },
    ),
    "byteplus": ProviderMeta(
        display_name="BytePlus ModelArk",
        description="BytePlus ModelArk AI 平臺，支援豆包文字模型和 Seedance 影片生成，具備音訊生成和種子控制能力。",
        required_keys=["api_key"],
        optional_keys=["video_max_workers"],
        secret_keys=["api_key"],
        models={
            # --- text ---
            "doubao-seed-2-0-pro-260215": ModelInfo(
                display_name="豆包 Seed 2.0 Pro",
                media_type="text",
                capabilities=["text_generation", "vision"],
            ),
            "doubao-seed-2-0-lite-260215": ModelInfo(
                display_name="豆包 Seed 2.0 Lite",
                media_type="text",
                capabilities=["text_generation", "vision"],
                default=True,
            ),
            "doubao-seed-2-0-mini-260215": ModelInfo(
                display_name="豆包 Seed 2.0 Mini",
                media_type="text",
                capabilities=["text_generation", "vision"],
            ),
            "doubao-seed-1-8-251228": ModelInfo(
                display_name="豆包 Seed 1.8",
                media_type="text",
                capabilities=["text_generation", "structured_output", "vision"],
            ),
            # --- video ---
            "doubao-seedance-2-0-260128": ModelInfo(
                display_name="Seedance 2.0",
                media_type="video",
                capabilities=["text_to_video", "image_to_video", "generate_audio", "seed_control", "video_extend"],
                default=True,
                supported_durations=list(range(4, 16)),
                supported_resolutions=["480p", "720p", "1080p"],
            ),
        },
    ),
    "grok": ProviderMeta(
        display_name="Grok",
        description="xAI Grok 模型，支援影片和圖片生成。",
        required_keys=["api_key"],
        optional_keys=["video_max_workers", "image_max_workers"],
        secret_keys=["api_key"],
        models={
            # --- text ---
            "grok-4.20-0309-reasoning": ModelInfo(
                display_name="Grok 4.20 Reasoning",
                media_type="text",
                capabilities=["text_generation", "structured_output", "vision"],
            ),
            "grok-4.20-0309-non-reasoning": ModelInfo(
                display_name="Grok 4.20 Non-Reasoning",
                media_type="text",
                capabilities=["text_generation", "structured_output", "vision"],
            ),
            "grok-4-1-fast-reasoning": ModelInfo(
                display_name="Grok 4.1 Fast Reasoning",
                media_type="text",
                capabilities=["text_generation", "structured_output", "vision"],
                default=True,
            ),
            "grok-4-1-fast-non-reasoning": ModelInfo(
                display_name="Grok 4.1 Fast (Non-Reasoning)",
                media_type="text",
                capabilities=["text_generation", "structured_output", "vision"],
            ),
            # --- image ---
            "grok-imagine-image-pro": ModelInfo(
                display_name="Grok Imagine Image Pro",
                media_type="image",
                supported_image_sizes=["1K", "2K"],
                capabilities=["text_to_image", "image_to_image"],
            ),
            "grok-imagine-image": ModelInfo(
                display_name="Grok Imagine Image",
                media_type="image",
                supported_image_sizes=["1K", "2K"],
                capabilities=["text_to_image", "image_to_image"],
                default=True,
            ),
            # --- video ---
            "grok-imagine-video": ModelInfo(
                display_name="Grok Imagine Video",
                media_type="video",
                capabilities=["text_to_video", "image_to_video"],
                default=True,
                supported_durations=list(range(1, 16)),
            ),
        },
    ),
    "openai": ProviderMeta(
        display_name="OpenAI",
        description="OpenAI 官方平臺，支援 GPT-5.5 文字、GPT Image 圖片和 Sora 影片生成。",
        required_keys=["api_key"],
        optional_keys=["base_url", "image_max_workers", "video_max_workers"],
        secret_keys=["api_key"],
        models={
            # --- text ---
            "gpt-5.5": ModelInfo(
                display_name="GPT-5.5",
                media_type="text",
                capabilities=["text_generation", "structured_output", "vision"],
            ),
            "gpt-5.5-mini": ModelInfo(
                display_name="GPT-5.5 Mini",
                media_type="text",
                capabilities=["text_generation", "structured_output", "vision"],
                default=True,
            ),
            "gpt-5.5-nano": ModelInfo(
                display_name="GPT-5.5 Nano",
                media_type="text",
                capabilities=["text_generation", "structured_output", "vision"],
            ),
            # --- image ---
            "gpt-image-2": ModelInfo(
                display_name="GPT Image 2",
                media_type="image",
                supported_image_sizes=["512PX", "1K", "2K", "4K"],
                capabilities=["text_to_image", "image_to_image"],
                default=True,
            ),
            "gpt-image-2-2026-04-21": ModelInfo(
                display_name="GPT Image 2 (2026-04-21)",
                media_type="image",
                supported_image_sizes=["512PX", "1K", "2K", "4K"],
                capabilities=["text_to_image", "image_to_image"],
            ),
            # --- video ---
            "sora-2": ModelInfo(
                display_name="Sora 2",
                media_type="video",
                capabilities=["text_to_video", "image_to_video"],
                default=True,
                supported_durations=[4, 8, 12],
            ),
            "sora-2-pro": ModelInfo(
                display_name="Sora 2 Pro",
                media_type="video",
                capabilities=["text_to_video", "image_to_video"],
                supported_durations=[4, 8, 12],
            ),
        },
    ),
    "ai360": ProviderMeta(
        display_name="ai360 Video Studio",
        description="ai360 自託管影片生成服務，以帳號密碼登入取得 JWT，支援文字轉影片與參考圖生影片。",
        required_keys=["username", "password", "base_url"],
        optional_keys=["project_id", "video_max_workers"],
        secret_keys=["password"],
        models={
            # --- video ---
            "ai360-video": ModelInfo(
                display_name="ai360 Video",
                media_type="video",
                capabilities=["text_to_video", "image_to_video", "generate_audio"],
                default=True,
                supported_durations=list(range(4, 16)),
                supported_resolutions=["480p", "720p", "1080p"],
            ),
        },
    ),
}
