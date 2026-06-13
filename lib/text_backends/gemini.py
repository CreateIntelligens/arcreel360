"""Gemini 文字生成後端。"""

from __future__ import annotations

import logging
from pathlib import Path

try:
    from google import genai
    from PIL import Image
except ImportError:
    genai = None  # type: ignore
    Image = None  # type: ignore

from ..config.url_utils import normalize_base_url
from ..gemini_shared import VERTEX_SCOPES, with_retry_async
from ..providers import PROVIDER_GEMINI
from .base import (
    TextCapability,
    TextGenerationRequest,
    TextGenerationResult,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-3.1-flash-lite"


class GeminiTextBackend:
    """Gemini 文字生成後端，支援 AI Studio 和 Vertex AI 兩種模式。"""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        backend: str = "aistudio",
        base_url: str | None = None,
        gcs_bucket: str | None = None,
    ):
        self._model = model or DEFAULT_MODEL
        raw_backend = backend or "aistudio"
        self._backend = str(raw_backend).strip().lower() or "aistudio"

        if self._backend == "vertex":
            import json as json_module

            from google.oauth2 import service_account

            from ..system_config import resolve_vertex_credentials_path

            credentials_file = resolve_vertex_credentials_path(Path(__file__).parent.parent.parent)
            if credentials_file is None:
                raise ValueError("未找到 Vertex AI 憑證檔案\n請將服務賬號 JSON 檔案放入 vertex_keys/ 目錄")

            with open(credentials_file) as f:
                creds_data = json_module.load(f)
            project_id = creds_data.get("project_id")

            if not project_id:
                raise ValueError(f"憑證檔案 {credentials_file} 中未找到 project_id")

            credentials = service_account.Credentials.from_service_account_file(
                str(credentials_file), scopes=VERTEX_SCOPES
            )

            self._client = genai.Client(
                vertexai=True,
                project=project_id,
                location="global",
                credentials=credentials,
            )
            logger.info("GeminiTextBackend: 使用 Vertex AI 後端（憑證: %s）", credentials_file.name)
        else:
            if not api_key:
                raise ValueError("Gemini API Key 未提供（API Key is required for AI Studio mode）。")
            effective_base_url = normalize_base_url(base_url)
            http_options = {"base_url": effective_base_url} if effective_base_url else None
            self._client = genai.Client(api_key=api_key, http_options=http_options)
            if base_url:
                logger.info("GeminiTextBackend: 使用 AI Studio 後端（Base URL: %s）", base_url)
            else:
                logger.info("GeminiTextBackend: 使用 AI Studio 後端")

    @property
    def name(self) -> str:
        return PROVIDER_GEMINI

    @property
    def model(self) -> str:
        return self._model

    @property
    def capabilities(self) -> set[TextCapability]:
        return {
            TextCapability.TEXT_GENERATION,
            TextCapability.STRUCTURED_OUTPUT,
            TextCapability.VISION,
        }

    def _build_config(
        self,
        response_schema: dict | type | None,
        system_prompt: str | None,
        max_output_tokens: int | None,
    ) -> dict:
        """構建 generate_content 的 config 字典。"""
        config: dict = {}
        if response_schema:
            config["response_mime_type"] = "application/json"
            if isinstance(response_schema, type):
                config["response_schema"] = response_schema
            else:
                config["response_json_schema"] = response_schema
        if system_prompt:
            config["system_instruction"] = system_prompt
        if max_output_tokens is not None:
            config["max_output_tokens"] = max_output_tokens
        return config

    def _build_contents(self, request: TextGenerationRequest) -> list:
        """構建 contents 列表（圖片 parts + 文字 prompt）。"""
        contents: list = []

        if request.images:
            for img_input in request.images:
                if img_input.path is not None:
                    pil_img = Image.open(img_input.path)
                    contents.append(pil_img)
                elif img_input.url is not None:
                    # URL 型圖片直接作為字串傳遞，SDK 內部會處理
                    contents.append(img_input.url)

        contents.append(request.prompt)
        return contents

    @with_retry_async()
    async def generate(self, request: TextGenerationRequest) -> TextGenerationResult:
        """非同步生成文字，支援結構化輸出和 vision。"""
        config = self._build_config(
            request.response_schema,
            request.system_prompt,
            request.max_output_tokens,
        )
        contents = self._build_contents(request)

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=contents,
            config=config if config else None,
        )

        text = response.text.strip() if response.text else ""

        input_tokens: int | None = None
        output_tokens: int | None = None
        if response.usage_metadata is not None:
            input_tokens = getattr(response.usage_metadata, "prompt_token_count", None)
            output_tokens = getattr(response.usage_metadata, "candidates_token_count", None)

        candidates = getattr(response, "candidates", None) or []
        if candidates:
            finish_reason = getattr(candidates[0], "finish_reason", None)
            reason_name = getattr(finish_reason, "name", str(finish_reason) if finish_reason else "")
            if reason_name == "MAX_TOKENS":
                logger.warning(
                    "Gemini 回應因 max_output_tokens (%s) 截斷,輸出 %s tokens — 下游 JSON parse 可能不完整",
                    request.max_output_tokens,
                    output_tokens,
                )

        return TextGenerationResult(
            text=text,
            provider=PROVIDER_GEMINI,
            model=self._model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
