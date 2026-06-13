"""ArkVideoBackend — BytePlus ModelArk 影片生成後端。"""

from __future__ import annotations

import asyncio
import logging

from lib.ark_shared import create_ark_client
from lib.providers import PROVIDER_BYTEPLUS
from lib.retry import BASE_RETRYABLE_ERRORS, _should_retry, with_retry_async
from lib.video_backends.base import (
    VideoCapability,
    VideoGenerationRequest,
    VideoGenerationResult,
    download_video,
)

logger = logging.getLogger(__name__)


class ArkVideoBackend:
    """BytePlus ModelArk 影片生成後端。"""

    DEFAULT_MODEL = "doubao-seedance-2-0-260128"

    _SEEDANCE_2_CAPABILITIES: set[VideoCapability] = {
        VideoCapability.TEXT_TO_VIDEO,
        VideoCapability.IMAGE_TO_VIDEO,
        VideoCapability.GENERATE_AUDIO,
        VideoCapability.SEED_CONTROL,
    }

    _MODEL_CAPABILITIES: dict[str, set[VideoCapability]] = {
        "doubao-seedance-2-0-260128": _SEEDANCE_2_CAPABILITIES,
    }

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
    ):
        self._client = create_ark_client(api_key=api_key)
        self._model = model or self.DEFAULT_MODEL
        self._capabilities = self._capabilities_for_model(self._model)

    @classmethod
    def _capabilities_for_model(cls, model: str) -> set[VideoCapability]:
        if model.startswith("ep-"):
            return cls._SEEDANCE_2_CAPABILITIES
        return cls._MODEL_CAPABILITIES.get(model, cls._SEEDANCE_2_CAPABILITIES)

    @property
    def name(self) -> str:
        return PROVIDER_BYTEPLUS

    @property
    def model(self) -> str:
        return self._model

    @property
    def capabilities(self) -> set[VideoCapability]:
        return self._capabilities

    async def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        """生成影片。任務建立和輪詢階段分離重試，避免瞬態錯誤導致重建任務。"""
        task_id = await self._create_task(request)
        return await self._poll_until_done(task_id, request)

    @with_retry_async()
    async def _create_task(self, request: VideoGenerationRequest) -> str:
        """建立 Ark 影片生成任務（帶重試保護）。"""
        # 1. Build content list
        content = [{"type": "text", "text": request.prompt}]

        if request.start_image:
            from lib.image_backends.base import image_to_base64_data_uri

            data_uri = image_to_base64_data_uri(request.start_image)
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": data_uri},
                }
            )

        # 2. Build API params
        create_params = {
            "model": self._model,
            "content": content,
            "ratio": request.aspect_ratio,
            "duration": request.duration_seconds,
            "resolution": request.resolution,
            "generate_audio": request.generate_audio,
            "watermark": False,
        }
        if request.seed is not None:
            create_params["seed"] = request.seed

        # 3. Create task (sync SDK call, run in executor)
        try:
            create_result = await asyncio.to_thread(
                self._client.content_generation.tasks.create,
                **create_params,
            )
        except Exception as e:
            err_msg = str(e)
            if "InputImageSensitiveContentDetected" in err_msg or "PrivacyInformation" in err_msg:
                raise RuntimeError(
                    "火山引擎安全攔截：輸入的分鏡圖被安全系統判定為「可能包含真人隱私資訊」。\n"
                    "建議解決方法：請生成該鏡頭的分鏡圖（可於提示詞加上動漫、插畫風格，或調整提示詞避免人像過於逼真逼真），再生成影片。"
                ) from e
            if "InvalidEndpointOrModel" in err_msg or "NotFound" in err_msg or "not exist" in err_msg:
                if not self._model.startswith("ep-"):
                    raise RuntimeError(
                        f"火山引擎 (BytePlus ModelArk) 影片生成失敗：找不到模型或接入點。您的模型設定為 '{self._model}'。\n"
                        f"請注意，火山引擎通常不支援直接使用原生模型名稱，您必須使用以 'ep-' 開頭的 Endpoint ID (接入點 ID)。\n"
                        f"請前往「全域設定 -> 模型選擇」配置您的 byteplus_video_endpoint_id，或在設定中直接使用有效的 'ep-...' 接入點。"
                    ) from e
            raise
        logger.info("Ark 任務已建立: %s", create_result.id)
        return create_result.id

    async def _poll_until_done(self, task_id: str, request: VideoGenerationRequest) -> VideoGenerationResult:
        """輪詢任務狀態直到完成，瞬態錯誤僅重試當次輪詢請求。"""
        poll_interval = 10
        max_wait_time = 600
        elapsed = 0

        while True:
            try:
                result = await asyncio.to_thread(
                    self._client.content_generation.tasks.get,
                    task_id=task_id,
                )
            except Exception as e:
                if _should_retry(e, BASE_RETRYABLE_ERRORS):
                    logger.warning("Ark 輪詢異常（將重試）: %s - %s", type(e).__name__, str(e)[:200])
                    elapsed += poll_interval
                    if elapsed >= max_wait_time:
                        raise
                    await asyncio.sleep(poll_interval)
                    continue
                raise

            if result.status == "succeeded":
                break
            elif result.status in ("failed", "expired"):
                error_msg = str(getattr(result, "error", None) or "Unknown error")
                if "InputImageSensitiveContentDetected" in error_msg or "PrivacyInformation" in error_msg:
                    raise RuntimeError(
                        "火山引擎安全攔截：輸入的分鏡圖被安全系統判定為「可能包含真人隱私資訊」。\n"
                        "建議解決方法：請生成該鏡頭的分鏡圖（可於提示詞加上動漫、插畫風格，或調整提示詞避免人像過於逼真），再生成影片。"
                    )
                raise RuntimeError(f"Ark 影片生成失敗: {error_msg}")

            elapsed += poll_interval
            if elapsed >= max_wait_time:
                raise TimeoutError(f"Ark 影片生成超時（{max_wait_time}秒）")

            logger.info(
                "Ark 影片生成中... 狀態: %s, 已等待 %d 秒",
                result.status,
                elapsed,
            )
            await asyncio.sleep(poll_interval)

        # Download video
        video_url = result.content.video_url
        await download_video(video_url, request.output_path)

        # Extract result metadata
        seed = getattr(result, "seed", None)
        usage_tokens = None
        if hasattr(result, "usage") and result.usage:
            usage_tokens = getattr(result.usage, "completion_tokens", None)

        return VideoGenerationResult(
            video_path=request.output_path,
            provider=PROVIDER_BYTEPLUS,
            model=self._model,
            duration_seconds=request.duration_seconds,
            video_uri=video_url,
            seed=seed,
            usage_tokens=usage_tokens,
            task_id=task_id,
            generate_audio=request.generate_audio,
        )
