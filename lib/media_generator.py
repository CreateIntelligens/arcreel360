"""
MediaGenerator 中間層

封裝 GeminiClient + VersionManager，提供"呼叫方無感"的版本管理。
呼叫方只需傳入 project_path 和 resource_id，版本管理自動完成。

覆蓋的 4 種資源型別：
- storyboards: 分鏡圖 (scene_E1S01.png)
- videos: 影片 (scene_E1S01.mp4)
- characters: 角色設計圖 (姜月茴.png)
- clues: 線索設計圖 (玉佩.png)
"""

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from PIL import Image

if TYPE_CHECKING:
    from lib.config.resolver import ConfigResolver
    from lib.image_backends.base import ImageBackend

from lib.db.base import DEFAULT_USER_ID
from lib.gemini_shared import RateLimiter
from lib.usage_tracker import UsageTracker
from lib.version_manager import VersionManager

logger = logging.getLogger(__name__)

# 所有圖片生成都會在 prompt 後自動附加此指示，避免生成的畫面出現文字/字幕/浮水印。
# 不顯示於前端、不寫入呼叫方傳入的 prompt，由後端統一強制注入。
IMAGE_NO_TEXT_DIRECTIVE = (
    "Important: do not render any text, letters, words, captions, subtitles, "
    "watermarks, logos, signage, or written characters anywhere in the image."
)

STRICT_REFERENCE_IMAGE_DIRECTIVE = (
    "Strict reference image rule: use every supplied reference image as authoritative visual guidance. "
    "Preserve the referenced subject identity, face, body shape, clothing, object design, materials, "
    "colors, layout, composition, environment style, and camera framing as closely as possible. "
    "Do not reinterpret, redesign, replace, omit, or ignore referenced elements. "
    "If the text prompt conflicts with the reference image, the reference image wins; "
    "only change details explicitly requested by the prompt."
)

# 影片生成的負面提示詞預設值（在既有的「無背景音樂」基礎上補上「無文字」）。
DEFAULT_VIDEO_NEGATIVE_PROMPT = (
    "background music, BGM, soundtrack, musical accompaniment, "
    "text, letters, words, captions, subtitles, watermark, logo, signage"
)


def _with_no_text_directive(prompt: str) -> str:
    """為圖片 prompt 附加「不要文字」指示。"""
    base = (prompt or "").rstrip()
    if not base:
        return IMAGE_NO_TEXT_DIRECTIVE
    return f"{base}\n\n{IMAGE_NO_TEXT_DIRECTIVE}"


def _with_strict_reference_directive(prompt: str) -> str:
    """有參考圖時附加嚴格參考指示。"""
    base = (prompt or "").rstrip()
    if STRICT_REFERENCE_IMAGE_DIRECTIVE in base:
        return base
    if not base:
        return STRICT_REFERENCE_IMAGE_DIRECTIVE
    return f"{base}\n\n{STRICT_REFERENCE_IMAGE_DIRECTIVE}"


class MediaGenerator:
    """
    媒體生成器中間層

    封裝 GeminiClient + VersionManager，提供自動版本管理。
    """

    # 資源型別到輸出路徑模式的對映
    OUTPUT_PATTERNS = {
        "storyboards": "storyboards/scene_{resource_id}.png",
        "videos": "videos/scene_{resource_id}.mp4",
        "characters": "characters/{resource_id}.png",
        "clues": "clues/{resource_id}.png",
        "scenes": "scenes/{resource_id}.png",
    }

    def __init__(
        self,
        project_path: Path,
        rate_limiter: RateLimiter | None = None,
        image_backend: Optional["ImageBackend"] = None,
        video_backend=None,
        *,
        config_resolver: Optional["ConfigResolver"] = None,
        user_id: str = DEFAULT_USER_ID,
    ):
        """
        初始化 MediaGenerator

        Args:
            project_path: 專案根目錄路徑
            rate_limiter: 可選的限流器例項
            image_backend: 可選的 ImageBackend 例項（用於圖片生成）
            video_backend: 可選的 VideoBackend 例項（用於影片生成）
            config_resolver: ConfigResolver 例項，用於執行時讀取配置
            user_id: 使用者 ID
        """
        self.project_path = Path(project_path)
        self.project_name = self.project_path.name
        self._rate_limiter = rate_limiter
        self._image_backend = image_backend
        self._video_backend = video_backend
        self._config = config_resolver
        self._user_id = user_id
        self.versions = VersionManager(project_path)

        # 初始化 UsageTracker（使用全域性 async session factory）
        self.usage_tracker = UsageTracker()

    @staticmethod
    def _sync(coro):
        """Run an async coroutine from synchronous code (e.g. inside to_thread)."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        return asyncio.run(coro)

    def _get_output_path(self, resource_type: str, resource_id: str) -> Path:
        """
        根據資源型別和 ID 推斷輸出路徑

        Args:
            resource_type: 資源型別 (storyboards, videos, characters, clues)
            resource_id: 資源 ID (E1S01, 姜月茴, 玉佩)

        Returns:
            輸出檔案的絕對路徑
        """
        if resource_type not in self.OUTPUT_PATTERNS:
            raise ValueError(f"不支援的資源型別: {resource_type}")

        pattern = self.OUTPUT_PATTERNS[resource_type]
        relative_path = pattern.format(resource_id=resource_id)
        output_path = (self.project_path / relative_path).resolve()
        try:
            output_path.relative_to(self.project_path.resolve())
        except ValueError:
            raise ValueError(f"非法資源 ID: '{resource_id}'")
        return output_path

    def _ensure_parent_dir(self, output_path: Path) -> None:
        """確保輸出目錄存在"""
        output_path.parent.mkdir(parents=True, exist_ok=True)

    def generate_image(
        self,
        prompt: str,
        resource_type: str,
        resource_id: str,
        reference_images=None,
        aspect_ratio: str = "9:16",
        image_size: str = "1K",
        **version_metadata,
    ) -> tuple[Path, int]:
        """
        生成圖片（帶自動版本管理，同步包裝）

        Args:
            prompt: 圖片生成提示詞
            resource_type: 資源型別 (storyboards, characters, clues)
            resource_id: 資源 ID (E1S01, 姜月茴, 玉佩)
            reference_images: 參考圖片列表
            aspect_ratio: 寬高比，預設 9:16（豎屏）
            image_size: 圖片尺寸，預設 1K
            **version_metadata: 額外後設資料

        Returns:
            (output_path, version_number) 元組
        """
        return self._sync(
            self.generate_image_async(
                prompt=prompt,
                resource_type=resource_type,
                resource_id=resource_id,
                reference_images=reference_images,
                aspect_ratio=aspect_ratio,
                image_size=image_size,
                **version_metadata,
            )
        )

    async def generate_image_async(
        self,
        prompt: str,
        resource_type: str,
        resource_id: str,
        reference_images=None,
        aspect_ratio: str = "9:16",
        image_size: str = "1K",
        **version_metadata,
    ) -> tuple[Path, int]:
        """
        非同步生成圖片（帶自動版本管理）

        Args:
            prompt: 圖片生成提示詞
            resource_type: 資源型別 (storyboards, characters, clues)
            resource_id: 資源 ID (E1S01, 姜月茴, 玉佩)
            reference_images: 參考圖片列表
            aspect_ratio: 寬高比，預設 9:16（豎屏）
            image_size: 圖片尺寸，預設 1K
            **version_metadata: 額外後設資料

        Returns:
            (output_path, version_number) 元組
        """
        from lib.image_backends.base import ImageGenerationRequest, ReferenceImage

        # 先轉換參考圖，讓後續 prompt、usage、version 都能以實際送出的 refs 為準。
        ref_images: list[ReferenceImage] = []
        if reference_images:
            for ref in reference_images:
                if isinstance(ref, dict):
                    img_val = ref.get("image", "")
                    ref_images.append(
                        ReferenceImage(
                            path=str(img_val),
                            label=str(ref.get("label", "")),
                        )
                    )
                elif hasattr(ref, "__fspath__") or isinstance(ref, (str, Path)):
                    ref_images.append(ReferenceImage(path=str(ref)))
                # PIL Image 等不支援的型別忽略

        # 後端統一注入「不要文字」指示；有參考圖時再強制要求嚴格參考。
        effective_prompt = _with_no_text_directive(prompt)
        if ref_images:
            effective_prompt = _with_strict_reference_directive(effective_prompt)

        output_path = self._get_output_path(resource_type, resource_id)
        self._ensure_parent_dir(output_path)

        # 1. 若已存在，確保舊檔案被記錄
        if output_path.exists():
            self.versions.ensure_current_tracked(
                resource_type=resource_type,
                resource_id=resource_id,
                current_file=output_path,
                prompt=effective_prompt,
                aspect_ratio=aspect_ratio,
                **version_metadata,
            )

        if self._image_backend is None:
            raise RuntimeError("image_backend not configured")

        # 2. 記錄 API 呼叫開始
        call_id = await self.usage_tracker.start_call(
            project_name=self.project_name,
            call_type="image",
            model=self._image_backend.model,
            prompt=effective_prompt,
            resolution=image_size,
            aspect_ratio=aspect_ratio,
            provider=self._image_backend.name,
            user_id=self._user_id,
            segment_id=resource_id if resource_type in ("storyboards", "videos") else None,
        )

        try:
            # 3. 呼叫 ImageBackend
            request = ImageGenerationRequest(
                prompt=effective_prompt,
                output_path=output_path,
                reference_images=ref_images,
                aspect_ratio=aspect_ratio,
                image_size=image_size,
                project_name=self.project_name,
            )
            result = await self._image_backend.generate(request)

            # 4. 記錄呼叫成功
            await self.usage_tracker.finish_call(
                call_id=call_id,
                status="success",
                output_path=str(output_path),
                quality=getattr(result, "quality", None),
                size=getattr(result, "size", None),
            )
        except Exception as e:
            # 記錄呼叫失敗
            logger.exception("生成失敗 (%s)", "image")
            await self.usage_tracker.finish_call(
                call_id=call_id,
                status="failed",
                error_message=str(e),
            )
            raise

        # 5. 記錄新版本
        reference_images_metadata = [{"name": Path(ref.path).name, "label": ref.label} for ref in ref_images] or None
        new_version = self.versions.add_version(
            resource_type=resource_type,
            resource_id=resource_id,
            prompt=effective_prompt,
            source_file=output_path,
            aspect_ratio=aspect_ratio,
            image_size=image_size,
            reference_images=reference_images_metadata,
            model=self._image_backend.model,
            provider=self._image_backend.name,
            **version_metadata,
        )

        return output_path, new_version

    def generate_video(
        self,
        prompt: str,
        resource_type: str,
        resource_id: str,
        start_image: str | Path | Image.Image | None = None,
        aspect_ratio: str = "9:16",
        duration_seconds: str = "8",
        resolution: str = "1080p",
        negative_prompt: str = DEFAULT_VIDEO_NEGATIVE_PROMPT,
        **version_metadata,
    ) -> tuple[Path, int, any, str | None]:
        """
        生成影片（帶自動版本管理，同步包裝）

        Args:
            prompt: 影片生成提示詞
            resource_type: 資源型別 (videos)
            resource_id: 資源 ID (E1S01)
            start_image: 起始幀圖片（image-to-video 模式）
            aspect_ratio: 寬高比，預設 9:16（豎屏）
            duration_seconds: 影片時長，可選 "4", "6", "8"
            resolution: 解析度，預設 "1080p"
            negative_prompt: 負面提示詞
            **version_metadata: 額外後設資料

        Returns:
            (output_path, version_number, video_ref, video_uri) 四元組
        """
        return self._sync(
            self.generate_video_async(
                prompt=prompt,
                resource_type=resource_type,
                resource_id=resource_id,
                start_image=start_image,
                aspect_ratio=aspect_ratio,
                duration_seconds=duration_seconds,
                resolution=resolution,
                negative_prompt=negative_prompt,
                **version_metadata,
            )
        )

    async def generate_video_async(
        self,
        prompt: str,
        resource_type: str,
        resource_id: str,
        start_image: str | Path | Image.Image | None = None,
        aspect_ratio: str = "9:16",
        duration_seconds: str = "8",
        resolution: str = "1080p",
        negative_prompt: str = DEFAULT_VIDEO_NEGATIVE_PROMPT,
        **version_metadata,
    ) -> tuple[Path, int, any, str | None]:
        """
        非同步生成影片（帶自動版本管理）

        Args:
            prompt: 影片生成提示詞
            resource_type: 資源型別 (videos)
            resource_id: 資源 ID (E1S01)
            start_image: 起始幀圖片（image-to-video 模式）
            aspect_ratio: 寬高比，預設 9:16（豎屏）
            duration_seconds: 影片時長，可選 "4", "6", "8"
            resolution: 解析度，預設 "1080p"
            negative_prompt: 負面提示詞
            **version_metadata: 額外後設資料

        Returns:
            (output_path, version_number, video_ref, video_uri) 四元組
        """
        output_path = self._get_output_path(resource_type, resource_id)
        self._ensure_parent_dir(output_path)
        start_image_path = Path(start_image) if isinstance(start_image, (str, Path)) else None
        effective_prompt = _with_strict_reference_directive(prompt) if start_image_path else (prompt or "")

        # 1. 若已存在，確保舊檔案被記錄
        if output_path.exists():
            self.versions.ensure_current_tracked(
                resource_type=resource_type,
                resource_id=resource_id,
                current_file=output_path,
                prompt=effective_prompt,
                duration_seconds=duration_seconds,
                **version_metadata,
            )

        # 2. 記錄 API 呼叫開始
        try:
            duration_int = int(duration_seconds) if duration_seconds else 8
        except (ValueError, TypeError):
            duration_int = 8

        if self._video_backend is None:
            raise RuntimeError("video_backend not configured")

        model_name = self._video_backend.model
        provider_name = self._video_backend.name
        configured_generate_audio = (
            await self._config.video_generate_audio(self.project_name) if self._config else False
        )
        effective_generate_audio = version_metadata.get("generate_audio", configured_generate_audio)

        call_id = await self.usage_tracker.start_call(
            project_name=self.project_name,
            call_type="video",
            model=model_name,
            prompt=effective_prompt,
            resolution=resolution,
            duration_seconds=duration_int,
            aspect_ratio=aspect_ratio,
            generate_audio=effective_generate_audio,
            provider=provider_name,
            user_id=self._user_id,
            segment_id=resource_id if resource_type in ("storyboards", "videos") else None,
        )

        try:
            from lib.video_backends.base import VideoGenerationRequest

            request = VideoGenerationRequest(
                prompt=effective_prompt,
                output_path=output_path,
                aspect_ratio=aspect_ratio,
                duration_seconds=duration_int,
                resolution=resolution,
                start_image=start_image_path,
                generate_audio=effective_generate_audio,
                negative_prompt=negative_prompt,
                project_name=self.project_name,
                seed=version_metadata.get("seed"),
            )

            result = await self._video_backend.generate(request)
            video_ref = None
            video_uri = result.video_uri
            actual_duration_seconds = result.duration_seconds
            adjusted = result.adjusted

            # Track usage with provider info
            await self.usage_tracker.finish_call(
                call_id=call_id,
                status="success",
                output_path=str(output_path),
                usage_tokens=result.usage_tokens,
                generate_audio=result.generate_audio,
            )
        except Exception as e:
            # 記錄呼叫失敗
            logger.exception("生成失敗 (%s)", "video")
            await self.usage_tracker.finish_call(
                call_id=call_id,
                status="failed",
                error_message=str(e),
            )
            raise

        # 5. 記錄新版本
        if adjusted:
            version_metadata["adjusted"] = adjusted

        new_version = self.versions.add_version(
            resource_type=resource_type,
            resource_id=resource_id,
            prompt=effective_prompt,
            source_file=output_path,
            duration_seconds=actual_duration_seconds,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            negative_prompt=negative_prompt,
            model=model_name,
            provider=provider_name,
            **version_metadata,
        )

        return output_path, new_version, video_ref, video_uri
