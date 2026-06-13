"""ArkTextBackend — BytePlus ModelArk 文字生成後端。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from lib.ark_shared import ARK_BASE_URL, create_ark_client, resolve_ark_api_key
from lib.providers import PROVIDER_BYTEPLUS
from lib.retry import with_retry_async
from lib.text_backends.base import (
    TextCapability,
    TextGenerationRequest,
    TextGenerationResult,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "doubao-seed-2-0-lite-260215"


class ArkTextBackend:
    """BytePlus ModelArk 文字生成後端。"""

    def __init__(self, *, api_key: str | None = None, model: str | None = None):
        self._client = create_ark_client(api_key=api_key)
        # Instructor 要求 openai.OpenAI 例項；Ark SDK client 型別不相容，
        # 但 Ark API 是 OpenAI 相容的，因此額外建立原生 OpenAI 客戶端供降級使用。
        from openai import OpenAI

        self._openai_client = OpenAI(base_url=ARK_BASE_URL, api_key=resolve_ark_api_key(api_key))
        self._model = model or DEFAULT_MODEL
        self._capabilities: set[TextCapability] = self._resolve_capabilities()

    def _resolve_capabilities(self) -> set[TextCapability]:
        """根據 PROVIDER_REGISTRY 中的模型宣告構建能力集合。"""
        from lib.config.registry import PROVIDER_REGISTRY

        base = {TextCapability.TEXT_GENERATION, TextCapability.VISION}
        provider_meta = PROVIDER_REGISTRY.get(PROVIDER_BYTEPLUS)
        if provider_meta:
            model_info = provider_meta.models.get(self._model)
            if model_info and TextCapability.STRUCTURED_OUTPUT in model_info.capabilities:
                base.add(TextCapability.STRUCTURED_OUTPUT)
        # 未註冊模型不加 STRUCTURED_OUTPUT：寧可走 Instructor 降級也不呼叫會報錯的原生 API
        return base

    @property
    def name(self) -> str:
        return PROVIDER_BYTEPLUS

    @property
    def model(self) -> str:
        return self._model

    @property
    def capabilities(self) -> set[TextCapability]:
        return self._capabilities

    @with_retry_async()
    async def generate(self, request: TextGenerationRequest) -> TextGenerationResult:
        if request.images:
            return await self._generate_vision(request)
        if request.response_schema:
            return await self._generate_structured(request)
        return await self._generate_plain(request)

    async def _generate_plain(self, request: TextGenerationRequest) -> TextGenerationResult:
        messages = self._build_messages(request)
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
        }
        if request.max_output_tokens is not None:
            kwargs["max_tokens"] = request.max_output_tokens

        response = await asyncio.to_thread(
            self._client.chat.completions.create,
            **kwargs,
        )
        return self._parse_chat_response(response, request.max_output_tokens)

    async def _generate_structured(self, request: TextGenerationRequest) -> TextGenerationResult:
        messages = self._build_messages(request)

        if TextCapability.STRUCTURED_OUTPUT in self._capabilities:
            from lib.text_backends.base import resolve_schema

            schema = resolve_schema(request.response_schema)
            kwargs: dict[str, Any] = {
                "model": self._model,
                "messages": messages,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "response",
                        "schema": schema,
                    },
                },
            }
            if request.max_output_tokens is not None:
                kwargs["max_tokens"] = request.max_output_tokens

            try:
                response = await asyncio.to_thread(
                    self._client.chat.completions.create,
                    **kwargs,
                )
                return self._parse_chat_response(response, request.max_output_tokens)
            except Exception as exc:
                logger.warning("原生 response_format 失敗 (%s)，降級到 Instructor/json_object 路徑", exc)

        return await self._structured_fallback(request, messages)

    async def _structured_fallback(self, request: TextGenerationRequest, messages: list[dict]) -> TextGenerationResult:
        """Instructor / json_object 降級路徑。"""
        from lib.text_backends.instructor_support import instructor_fallback_sync

        return await asyncio.to_thread(
            instructor_fallback_sync,
            client=self._openai_client,
            model=self._model,
            messages=messages,
            response_schema=request.response_schema,
            provider=PROVIDER_BYTEPLUS,
            max_output_tokens=request.max_output_tokens,
        )

    async def _generate_vision(self, request: TextGenerationRequest) -> TextGenerationResult:
        content: list[dict[str, Any]] = []
        for img in request.images or []:
            if img.path:
                from lib.image_backends.base import image_to_base64_data_uri

                data_uri = image_to_base64_data_uri(img.path)
                content.append({"type": "input_image", "image_url": data_uri})
            elif img.url:
                content.append({"type": "input_image", "image_url": img.url})

        content.append({"type": "input_text", "text": request.prompt})

        messages: list[dict] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": content})

        kwargs: dict[str, Any] = {
            "model": self._model,
            "input": messages,
        }
        if request.max_output_tokens is not None:
            kwargs["max_tokens"] = request.max_output_tokens

        response = await asyncio.to_thread(
            self._client.responses.create,
            **kwargs,
        )

        text = response.output_text if hasattr(response, "output_text") else str(response)
        input_tokens = getattr(getattr(response, "usage", None), "input_tokens", None)
        output_tokens = getattr(getattr(response, "usage", None), "output_tokens", None)

        return TextGenerationResult(
            text=text.strip() if isinstance(text, str) else str(text),
            provider=PROVIDER_BYTEPLUS,
            model=self._model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    def _build_messages(self, request: TextGenerationRequest) -> list[dict]:
        messages: list[dict] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})
        return messages

    def _parse_chat_response(self, response, max_output_tokens: int | None = None) -> TextGenerationResult:
        choice = response.choices[0]
        if getattr(choice, "finish_reason", None) == "length":
            logger.warning(
                "Ark 回應因 max_tokens (%s) 截斷,輸出 %s tokens",
                max_output_tokens,
                response.usage.completion_tokens if getattr(response, "usage", None) else None,
            )
        text = choice.message.content
        input_tokens = getattr(getattr(response, "usage", None), "prompt_tokens", None)
        output_tokens = getattr(getattr(response, "usage", None), "completion_tokens", None)
        return TextGenerationResult(
            text=text.strip() if isinstance(text, str) else str(text),
            provider=PROVIDER_BYTEPLUS,
            model=self._model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
