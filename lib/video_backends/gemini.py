"""GeminiVideoBackend — 從 GeminiClient 提取的影片生成邏輯。"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import time
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image

from lib.config.registry import PROVIDER_REGISTRY
from lib.config.url_utils import normalize_base_url
from lib.gemini_shared import VERTEX_SCOPES, RateLimiter, get_shared_rate_limiter, with_retry_async
from lib.providers import PROVIDER_GEMINI
from lib.retry import BASE_RETRYABLE_ERRORS, _should_retry
from lib.system_config import resolve_vertex_credentials_path
from lib.video_backends.base import (
    VideoCapability,
    VideoGenerationRequest,
    VideoGenerationResult,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_RESOLUTION_ORDER = ["720p", "1080p", "4k"]


class VeoInvalidCombinationError(ValueError):
    """使用者可理解的 Veo 參數組合錯誤。"""

    def __init__(self, model: str):
        self.detail = {
            "code": "veo_invalid_combination",
            "message": "你選的 解析度/秒數/參考圖 組合 Veo 不支援",
            "model": model,
            "hint": "Lite 模型不支援 4k；1080p/4k 與 reference image 都會強制 8 秒",
        }
        super().__init__(f"{self.detail['message']}：{self.detail['hint']} (model={model})")


class GeminiVideoBackend:
    """Gemini (Veo) 影片生成後端。"""

    def __init__(
        self,
        *,
        backend_type: str = "aistudio",
        api_key: str | None = None,
        rate_limiter: RateLimiter | None = None,
        video_model: str | None = None,
        base_url: str | None = None,
    ):
        from google import genai as _genai
        from google.genai import types as _types

        self._types = _types
        self._rate_limiter = rate_limiter or get_shared_rate_limiter()
        self._backend_type = backend_type.strip().lower()
        self._credentials = None
        self._project_id = None

        from lib.cost_calculator import cost_calculator

        self._video_model = video_model or os.environ.get("GEMINI_VIDEO_MODEL", cost_calculator.DEFAULT_VIDEO_MODEL)

        if self._backend_type == "vertex":
            import json as json_module

            from google.oauth2 import service_account

            credentials_file = resolve_vertex_credentials_path(Path(__file__).parent.parent.parent)
            if credentials_file is None:
                raise ValueError("未找到 Vertex AI 憑證檔案")

            with open(credentials_file) as f:
                creds_data = json_module.load(f)
            self._project_id = creds_data.get("project_id")

            self._credentials = service_account.Credentials.from_service_account_file(
                str(credentials_file), scopes=VERTEX_SCOPES
            )

            self._client = _genai.Client(
                vertexai=True,
                project=self._project_id,
                location="global",
                credentials=self._credentials,
            )
        else:
            _api_key = api_key or os.environ.get("GEMINI_API_KEY")
            if not _api_key:
                raise ValueError("GEMINI_API_KEY 環境變數未設定")

            effective_base_url = normalize_base_url(base_url or os.environ.get("GEMINI_BASE_URL"))
            http_options = {"base_url": effective_base_url} if effective_base_url else None
            self._client = _genai.Client(api_key=_api_key, http_options=http_options)

        # 快取 capabilities，避免每次訪問建立新 set
        self._capabilities: set[VideoCapability] = {
            VideoCapability.TEXT_TO_VIDEO,
            VideoCapability.IMAGE_TO_VIDEO,
            VideoCapability.NEGATIVE_PROMPT,
            VideoCapability.VIDEO_EXTEND,
        }
        if self._backend_type == "vertex":
            self._capabilities.add(VideoCapability.GENERATE_AUDIO)

    @property
    def name(self) -> str:
        return f"gemini-{self._backend_type}"

    @property
    def model(self) -> str:
        return self._video_model

    @property
    def capabilities(self) -> set[VideoCapability]:
        return self._capabilities

    @staticmethod
    def _model_supports_negative_prompt(model: str) -> bool:
        """Veo 3.1 lite preview 與部分 preview 變體 API 拒收 negativePrompt。

        實測 veo-3.1-lite-generate-preview 會回 400 invalid argument。其他 Veo 3.1
        preview/GA 變體目前已知支援；此函式集中標記黑名單以便日後擴充。
        """
        if not model:
            return True
        return "lite" not in model.lower()

    @staticmethod
    def _normalize_duration(duration_seconds: int) -> str:
        """標準化為 Veo 支援的離散時長值: '4', '6', '8'。"""
        return str(GeminiVideoBackend._normalize_duration_value(duration_seconds))

    @staticmethod
    def _normalize_duration_value(duration_seconds: int) -> int:
        """標準化為 Veo 舊邏輯支援的離散時長值。"""
        if duration_seconds <= 4:
            return 4
        if duration_seconds <= 6:
            return 6
        return 8

    @staticmethod
    def _is_bad_request_error(exc: Exception) -> bool:
        status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        if status == 400:
            return True
        message = str(exc).lower()
        return "400" in message and ("invalid" in message or "unsupported" in message or "not supported" in message)

    def _resolve_request(
        self,
        request: VideoGenerationRequest,
    ) -> tuple[VideoGenerationRequest, dict[str, tuple[object, object]]]:
        provider_id = "gemini-vertex" if self._backend_type == "vertex" else "gemini-aistudio"
        model_meta = PROVIDER_REGISTRY[provider_id].models.get(self._video_model)
        adjusted: dict[str, tuple[object, object]] = {}

        if model_meta is None:
            duration = self._normalize_duration_value(request.duration_seconds)
            if duration != request.duration_seconds:
                adjusted["duration_seconds"] = (request.duration_seconds, duration)
            return replace(request, duration_seconds=duration), adjusted

        if model_meta.supported_resolutions and request.resolution not in model_meta.supported_resolutions:
            raise VeoInvalidCombinationError(self._video_model)

        if (
            request.start_image
            and model_meta.reference_image_force_duration is not None
            and request.duration_seconds != model_meta.reference_image_force_duration
        ):
            raise VeoInvalidCombinationError(self._video_model)

        allowed_durations = model_meta.duration_resolution_constraints.get(request.resolution)
        if allowed_durations is not None and request.duration_seconds not in allowed_durations:
            raise VeoInvalidCombinationError(self._video_model)

        if model_meta.supported_durations and request.duration_seconds not in model_meta.supported_durations:
            raise VeoInvalidCombinationError(self._video_model)

        return request, {}

    async def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        """生成影片。任務建立和輪詢階段分離重試，避免瞬態錯誤導致重建任務。"""
        resolved_request, adjusted = self._resolve_request(request)
        operation = await self._create_task(resolved_request)
        result = await self._poll_until_done(operation, resolved_request)
        result.adjusted = adjusted or None
        return result

    @with_retry_async()
    async def _create_task(self, request: VideoGenerationRequest) -> Any:
        """建立 Gemini 影片生成任務（帶重試保護）。"""
        # 1. 限流
        if self._rate_limiter:
            await self._rate_limiter.acquire_async(self._video_model)

        # 2. duration 已由 _resolve_request 對齊，這裡只轉成 SDK 要求的字串
        duration_str = self._normalize_duration(request.duration_seconds)

        # 3. 構建配置
        config_params: dict = {
            "aspect_ratio": request.aspect_ratio,
            "resolution": request.resolution,
            "duration_seconds": duration_str,
        }
        if self._model_supports_negative_prompt(self._video_model):
            config_params["negative_prompt"] = (
                request.negative_prompt or "music, BGM, background music, subtitles, low quality"
            )
        if self._backend_type == "vertex":
            config_params["generate_audio"] = request.generate_audio
        config = self._types.GenerateVideosConfig(**config_params)

        # 4. 準備 source（prompt + 可選起始幀）
        image_param = self._prepare_image_param(request.start_image) if request.start_image else None
        source = self._types.GenerateVideosSource(prompt=request.prompt, image=image_param)

        # 5. 呼叫 API
        try:
            operation = await self._client.aio.models.generate_videos(
                model=self._video_model, source=source, config=config
            )
        except Exception as exc:
            if self._video_model.startswith("veo-") and self._is_bad_request_error(exc):
                raise VeoInvalidCombinationError(self._video_model) from exc
            raise
        op_name = getattr(operation, "name", "unknown")
        logger.info("影片生成已提交, operation=%s", op_name)
        return operation

    async def _poll_until_done(self, operation: Any, request: VideoGenerationRequest) -> VideoGenerationResult:
        """輪詢任務狀態直到完成，瞬態錯誤僅重試當次輪詢請求。"""
        op_name = getattr(operation, "name", "unknown")
        logger.info("開始輪詢 operation=%s ...", op_name)

        start_time = time.monotonic()
        poll_interval = 20  # 與 Google 官方推薦一致
        max_wait_time = 600
        while not operation.done:
            elapsed = time.monotonic() - start_time
            if elapsed >= max_wait_time:
                raise TimeoutError(f"影片生成超時（{max_wait_time}秒）")
            await asyncio.sleep(poll_interval)
            try:
                operation = await self._client.aio.operations.get(operation)
            except Exception as e:
                if _should_retry(e, BASE_RETRYABLE_ERRORS):
                    logger.warning("Gemini 輪詢異常（將重試）: %s - %s", type(e).__name__, str(e)[:200])
                    continue
                raise
            if not operation.done:
                elapsed = time.monotonic() - start_time
                logger.info(
                    "影片生成中... 已等待 %.0f 秒 (operation=%s)",
                    elapsed,
                    op_name,
                )

        total_elapsed = time.monotonic() - start_time
        logger.info("影片生成完成, 總耗時 %.0f 秒, operation=%s", total_elapsed, op_name)

        # 檢查結果
        if not operation.response or not operation.response.generated_videos:
            error_detail = getattr(operation, "error", None)
            metadata = getattr(operation, "metadata", None)
            logger.error(
                "影片生成返回空結果: operation=%s, error=%s, metadata=%s, elapsed=%.0f秒",
                op_name,
                error_detail,
                metadata,
                total_elapsed,
            )
            if error_detail:
                raise RuntimeError(f"影片生成失敗: {error_detail}")
            raise RuntimeError(
                "影片生成失敗：API 返回空結果。這通常是由於輸入的提示詞或圖片觸發了 Gemini 的安全過濾器（Safety Filter）而導致生成內容被攔截。\n"
                "建議解決方法：請調整該鏡頭的提示詞（避免可能敏感的字眼），或生成、更換分鏡參考圖後再重試。"
            )

        # 提取並下載影片
        generated_video = operation.response.generated_videos[0]
        video_ref = generated_video.video
        video_uri = video_ref.uri if video_ref else None

        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        await self._download_video_with_retry(video_ref, request.output_path)

        return VideoGenerationResult(
            video_path=request.output_path,
            provider=PROVIDER_GEMINI,
            model=self._video_model,
            duration_seconds=request.duration_seconds,
            video_uri=video_uri,
            generate_audio=request.generate_audio if self._backend_type == "vertex" else True,
        )

    # ------------------------------------------------------------------
    # 內部輔助方法（從 GeminiClient 提取）
    # ------------------------------------------------------------------

    def _prepare_image_param(self, image: str | Path | Image.Image | None):
        """準備圖片引數用於 API 呼叫 — 提取自 GeminiClient。"""
        if image is None:
            return None

        mime_type_png = "image/png"

        if isinstance(image, (str, Path)):
            with open(image, "rb") as f:
                image_bytes = f.read()
            suffix = Path(image).suffix.lower()
            mime_types = {
                ".png": mime_type_png,
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".webp": "image/webp",
            }
            mime_type = mime_types.get(suffix, mime_type_png)
            return self._types.Image(image_bytes=image_bytes, mime_type=mime_type)
        elif isinstance(image, Image.Image):
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            image_bytes = buffer.getvalue()
            return self._types.Image(image_bytes=image_bytes, mime_type=mime_type_png)
        else:
            return image

    @with_retry_async()
    async def _download_video_with_retry(self, video_ref, output_path: Path) -> None:
        """下載影片（含瞬態錯誤重試）。"""
        await asyncio.to_thread(self._download_video, video_ref, output_path)

    def _download_video(self, video_ref, output_path: Path) -> None:
        """下載影片到本地檔案 — 提取自 GeminiClient。"""
        if self._backend_type == "vertex":
            if video_ref and hasattr(video_ref, "video_bytes") and video_ref.video_bytes:
                with open(output_path, "wb") as f:
                    f.write(video_ref.video_bytes)
            elif video_ref and hasattr(video_ref, "uri") and video_ref.uri:
                import urllib.request

                urllib.request.urlretrieve(video_ref.uri, str(output_path))
            else:
                raise RuntimeError("影片生成成功但無法獲取影片資料")
        else:
            # AI Studio 模式：使用 files.download
            self._client.files.download(file=video_ref)
            video_ref.save(str(output_path))
