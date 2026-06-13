"""影片生成服務層核心介面定義。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

import httpx

from lib.retry import with_retry_async

# 圖片字尾 → MIME 型別對映（多個後端共用）
IMAGE_MIME_TYPES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


@with_retry_async()
async def download_video(url: str, output_path: Path, *, timeout: int = 120) -> None:
    """從 URL 流式下載影片到本地檔案（含瞬態錯誤重試）。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient() as http_client:
        async with http_client.stream("GET", url, timeout=timeout) as resp:
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    f.write(chunk)


class VideoCapability(StrEnum):
    """影片後端支援的能力列舉。"""

    TEXT_TO_VIDEO = "text_to_video"
    IMAGE_TO_VIDEO = "image_to_video"
    GENERATE_AUDIO = "generate_audio"
    NEGATIVE_PROMPT = "negative_prompt"
    VIDEO_EXTEND = "video_extend"
    SEED_CONTROL = "seed_control"
    FLEX_TIER = "flex_tier"


@dataclass
class VideoGenerationRequest:
    """通用影片生成請求。各 Backend 忽略不支援的欄位。"""

    prompt: str
    output_path: Path
    aspect_ratio: str = "9:16"
    duration_seconds: int = 5
    resolution: str = "1080p"
    start_image: Path | None = None
    generate_audio: bool = True

    # Veo 特有
    negative_prompt: str | None = None

    # 專案上下文（用於構建檔案服務 URL 等）
    project_name: str | None = None

    # Seedance 特有
    seed: int | None = None


@dataclass
class VideoGenerationResult:
    """通用影片生成結果。"""

    video_path: Path
    provider: str
    model: str
    duration_seconds: int

    video_uri: str | None = None
    seed: int | None = None
    usage_tokens: int | None = None
    task_id: str | None = None
    generate_audio: bool | None = None
    adjusted: dict[str, tuple[object, object]] | None = None


class VideoBackend(Protocol):
    """影片生成後端協議。"""

    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    @property
    def capabilities(self) -> set[VideoCapability]: ...

    async def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult: ...
