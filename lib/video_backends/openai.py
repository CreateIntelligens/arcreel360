"""OpenAIVideoBackend — OpenAI Sora 影片生成後端。"""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image, ImageOps

from lib.openai_shared import OPENAI_RETRYABLE_ERRORS, create_openai_client
from lib.providers import PROVIDER_OPENAI
from lib.retry import with_retry_async
from lib.video_backends.base import (
    IMAGE_MIME_TYPES,
    VideoCapability,
    VideoGenerationRequest,
    VideoGenerationResult,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "sora-2"

_SIZE_MAP: dict[tuple[str, str], str] = {
    ("720p", "9:16"): "720x1280",
    ("720p", "16:9"): "1280x720",
    ("1080p", "9:16"): "1080x1920",
    ("1080p", "16:9"): "1920x1080",
    ("1024p", "9:16"): "1024x1792",
    ("1024p", "16:9"): "1792x1024",
}
_DEFAULT_SIZE = "720x1280"


def _resolve_size(resolution: str, aspect_ratio: str) -> str:
    return _SIZE_MAP.get((resolution, aspect_ratio), _DEFAULT_SIZE)


class OpenAIVideoBackend:
    """OpenAI Sora 影片生成後端。"""

    def __init__(self, *, api_key: str | None = None, model: str | None = None, base_url: str | None = None):
        self._client = create_openai_client(api_key=api_key, base_url=base_url)
        self._model = model or DEFAULT_MODEL
        self._capabilities: set[VideoCapability] = {
            VideoCapability.TEXT_TO_VIDEO,
            VideoCapability.IMAGE_TO_VIDEO,
        }

    @property
    def name(self) -> str:
        return PROVIDER_OPENAI

    @property
    def model(self) -> str:
        return self._model

    @property
    def capabilities(self) -> set[VideoCapability]:
        return self._capabilities

    async def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        kwargs: dict = {
            "prompt": request.prompt,
            "model": self._model,
            "seconds": _map_duration(request.duration_seconds),
            "size": _resolve_size(request.resolution, request.aspect_ratio),
        }

        temp_image_path = None
        if request.start_image and Path(request.start_image).exists():
            resolved_image_path = _resize_image_to_fit(Path(request.start_image), kwargs["size"])
            if resolved_image_path != Path(request.start_image):
                temp_image_path = resolved_image_path
            kwargs["input_reference"] = _encode_start_image(resolved_image_path)

        logger.info("OpenAI 影片生成開始: model=%s, seconds=%s", self._model, kwargs["seconds"])

        try:
            video = await self._create_video(**kwargs)

            if video.status == "failed":
                raise RuntimeError(f"Sora 影片生成失敗: {video.error}")

            content = await self._download_content_with_retry(video.id)
            request.output_path.parent.mkdir(parents=True, exist_ok=True)
            request.output_path.write_bytes(content.content)

            logger.info("OpenAI 影片下載完成: %s", request.output_path)

            return VideoGenerationResult(
                video_path=request.output_path,
                provider=PROVIDER_OPENAI,
                model=self._model,
                duration_seconds=int(video.seconds if video.seconds is not None else kwargs["seconds"]),
                task_id=video.id,
            )
        finally:
            if temp_image_path and temp_image_path.exists():
                try:
                    temp_image_path.unlink()
                    logger.info("已刪除臨時適配圖片: %s", temp_image_path.name)
                except Exception as e:
                    logger.warning("刪除臨時適配圖片失敗: %s", e)

    @with_retry_async(retryable_errors=OPENAI_RETRYABLE_ERRORS)
    async def _create_video(self, **kwargs):
        """影片生成（create_and_poll），帶獨立重試。"""
        return await self._client.videos.create_and_poll(**kwargs)

    @with_retry_async(
        max_attempts=5,
        backoff_seconds=(4, 8, 15, 30),
        retryable_errors=OPENAI_RETRYABLE_ERRORS,
    )
    async def _download_content_with_retry(self, video_id: str):
        """單獨重試內容下載，避免因下載失敗重新觸發影片生成。"""
        return await self._client.videos.download_content(video_id)


def _map_duration(seconds: int) -> str:
    if seconds <= 4:
        return "4"
    elif seconds <= 8:
        return "8"
    else:
        return "12"


def _encode_start_image(image_path: Path) -> tuple[str, bytes, str]:
    mime = IMAGE_MIME_TYPES.get(image_path.suffix.lower(), "image/png")
    return (image_path.name, image_path.read_bytes(), mime)


def _resize_image_to_fit(image_path: Path, target_size: str) -> Path:
    """如果圖片尺寸與 target_size (格式 WxH，如 1280x720) 不符，將其縮放到 target_size 並返回新檔案的路徑。"""
    try:
        tw, th = map(int, target_size.split("x"))
    except ValueError:
        return image_path

    try:
        with Image.open(image_path) as img:
            w, h = img.size
            if w == tw and h == th:
                return image_path

            logger.info("圖片尺寸不符，將 %s (%dx%d) 縮放為 %s 以符合 OpenAI 限制", image_path.name, w, h, target_size)
            resized_img = ImageOps.fit(img, (tw, th), Image.Resampling.LANCZOS)

            temp_path = image_path.parent / f"{image_path.stem}_resized_{target_size}{image_path.suffix}"
            resized_img.save(temp_path)
            return temp_path
    except Exception as e:
        logger.warning("檢測或縮放圖片尺寸失敗: %s", e)
        return image_path
