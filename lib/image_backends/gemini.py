"""GeminiImageBackend — 從 GeminiClient 提取的圖片生成邏輯。"""

from __future__ import annotations

import json as json_module
import logging
import os
from pathlib import Path

from PIL import Image

from lib.config.url_utils import normalize_base_url
from lib.gemini_shared import VERTEX_SCOPES, RateLimiter, get_shared_rate_limiter, with_retry_async
from lib.image_backends.base import (
    ImageCapability,
    ImageGenerationRequest,
    ImageGenerationResult,
    ReferenceImage,
)
from lib.providers import PROVIDER_GEMINI
from lib.system_config import resolve_vertex_credentials_path

logger = logging.getLogger(__name__)

# 跳過名稱推斷的檔名模式
SKIP_NAME_PATTERNS = ("scene_", "storyboard_", "output_")

# 預設圖片模型
DEFAULT_IMAGE_MODEL = "gemini-3.1-flash-image-preview"


class GeminiImageBackend:
    """Gemini 圖片生成後端，支援 AI Studio 和 Vertex AI。"""

    def __init__(
        self,
        *,
        backend_type: str = "aistudio",
        api_key: str | None = None,
        rate_limiter: RateLimiter | None = None,
        image_model: str | None = None,
        base_url: str | None = None,
        credentials_path: str | None = None,
    ):
        from google import genai as _genai
        from google.genai import types as _types

        self._types = _types
        self._rate_limiter = rate_limiter or get_shared_rate_limiter()
        self._backend_type = backend_type.strip().lower()
        self._image_model = image_model or os.environ.get("GEMINI_IMAGE_MODEL", DEFAULT_IMAGE_MODEL)

        if self._backend_type == "vertex":
            from google.oauth2 import service_account

            credentials_file: Path | None = None
            if credentials_path:
                credentials_file = Path(credentials_path)
            else:
                credentials_file = resolve_vertex_credentials_path(Path(__file__).parent.parent.parent)

            if credentials_file is None:
                raise ValueError("未找到 Vertex AI 憑證檔案")

            with open(credentials_file) as f:
                creds_data = json_module.load(f)
            project_id = creds_data.get("project_id")

            credentials = service_account.Credentials.from_service_account_file(
                str(credentials_file), scopes=VERTEX_SCOPES
            )

            self._client = _genai.Client(
                vertexai=True,
                project=project_id,
                location="global",
                credentials=credentials,
            )
        else:
            _api_key = api_key or os.environ.get("GEMINI_API_KEY")
            if not _api_key:
                raise ValueError("Gemini API Key 未提供。請在「全域性設定 → 供應商」頁面配置 API Key。")

            effective_base_url = normalize_base_url(base_url or os.environ.get("GEMINI_BASE_URL"))
            http_options = {"base_url": effective_base_url} if effective_base_url else None
            self._client = _genai.Client(api_key=_api_key, http_options=http_options)

        self._capabilities: set[ImageCapability] = {
            ImageCapability.TEXT_TO_IMAGE,
            ImageCapability.IMAGE_TO_IMAGE,
        }

    @property
    def name(self) -> str:
        return f"gemini-{self._backend_type}"

    @property
    def model(self) -> str:
        return self._image_model

    @property
    def capabilities(self) -> set[ImageCapability]:
        return self._capabilities

    @with_retry_async(max_attempts=5, backoff_seconds=(2, 4, 8, 16, 32))
    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        """非同步生成圖片。"""
        # 1. 限流
        if self._rate_limiter:
            await self._rate_limiter.acquire_async(self._image_model)

        # 2. 構建 contents（參考圖 + prompt）
        contents = self._build_contents_with_labeled_refs(request.prompt, request.reference_images)

        # 3. 構建配置
        config = self._types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=self._types.ImageConfig(
                aspect_ratio=request.aspect_ratio,
                image_size=request.image_size,
            ),
        )

        # 4. 呼叫非同步 API
        response = await self._client.aio.models.generate_content(
            model=self._image_model, contents=contents, config=config
        )

        # 5. 解析響應並儲存
        self._process_image_response(response, request.output_path)

        return ImageGenerationResult(
            image_path=request.output_path,
            provider=PROVIDER_GEMINI,
            model=self._image_model,
        )

    @staticmethod
    def _load_image_detached(image_path: str | Path) -> Image.Image:
        """從路徑載入圖片並與底層檔案控制代碼解綁。"""
        with Image.open(image_path) as img:
            return img.copy()

    @staticmethod
    def _extract_name_from_path(image_path: str | Path) -> str | None:
        """從圖片路徑推斷名稱。跳過 scene_/storyboard_/output_ 字首的檔案。"""
        path = Path(image_path)
        filename = path.stem
        for pattern in SKIP_NAME_PATTERNS:
            if filename.startswith(pattern):
                return None
        return filename

    def _build_contents_with_labeled_refs(
        self,
        prompt: str,
        reference_images: list[ReferenceImage] | None = None,
    ) -> list:
        """
        構建帶名稱標籤的 contents 列表。

        格式：[標籤1, 圖片1, 標籤2, 圖片2, ..., prompt]
        """
        contents: list = []

        if reference_images:
            labeled_refs: list[str] = []
            for ref in reference_images:
                # 確定標籤
                label = ref.label.strip() if ref.label else ""
                name = label or self._extract_name_from_path(ref.path)

                if name:
                    labeled_refs.append(name)
                    contents.append(name)

                # 載入圖片
                loaded_img = self._load_image_detached(ref.path)
                contents.append(loaded_img)

            if labeled_refs:
                logger.debug("參考圖片標籤: %s", ", ".join(labeled_refs))

        # prompt 放最後
        contents.append(prompt)
        return contents

    @staticmethod
    def _process_image_response(response, output_path: Path) -> Image.Image:
        """解析圖片生成響應並儲存到檔案。"""
        for part in response.parts:
            if part.inline_data is not None:
                image = part.as_image()
                output_path.parent.mkdir(parents=True, exist_ok=True)
                image.save(output_path)
                return image
        raise RuntimeError("API 未返回圖片")
