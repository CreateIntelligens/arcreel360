"""OpenAITextBackend — OpenAI 文字生成後端。"""

from __future__ import annotations

import logging

from openai import AsyncOpenAI, BadRequestError

from lib.openai_shared import OPENAI_RETRYABLE_ERRORS, create_openai_client
from lib.providers import PROVIDER_OPENAI
from lib.retry import with_retry_async
from lib.text_backends.base import (
    TextCapability,
    TextGenerationRequest,
    TextGenerationResult,
    resolve_schema,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-5.5-mini"


class OpenAITextBackend:
    """OpenAI 文字生成後端，支援 Chat Completions API。"""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        # 禁用 SDK 內建重試，由本層 generate() 統一管理重試策略
        self._client = create_openai_client(api_key=api_key, base_url=base_url, max_retries=0)
        self._model = model or DEFAULT_MODEL
        self._capabilities: set[TextCapability] = {
            TextCapability.TEXT_GENERATION,
            TextCapability.STRUCTURED_OUTPUT,
            TextCapability.VISION,
        }

    @property
    def name(self) -> str:
        return PROVIDER_OPENAI

    @property
    def model(self) -> str:
        return self._model

    @property
    def capabilities(self) -> set[TextCapability]:
        return self._capabilities

    @with_retry_async(max_attempts=4, backoff_seconds=(2, 4, 8), retryable_errors=OPENAI_RETRYABLE_ERRORS)
    async def generate(self, request: TextGenerationRequest) -> TextGenerationResult:
        """生成文字回復。

        單一重試迴圈包裹整個流程：
        1. 嘗試原生 response_format 呼叫
        2. 若遇 schema 不相容錯誤 → 本次 attempt 內降級到 Instructor
        3. 若遇瞬態錯誤（429/500/503/網路）→ 由裝飾器自動重試整個流程

        這樣無論是原生呼叫還是降級路徑遇到瞬態錯誤，都統一由外層重試處理。
        """
        messages = _build_messages(request)
        kwargs: dict = {"model": self._model, "messages": messages}

        if request.max_output_tokens is not None:
            kwargs["max_completion_tokens"] = request.max_output_tokens

        if request.response_schema:
            schema = resolve_schema(request.response_schema)
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "strict": True,
                    "schema": schema,
                },
            }

        try:
            response = await self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            if request.response_schema and _is_schema_error(exc):
                logger.warning(
                    "原生 response_format 失敗 (%s)，降級到 Instructor 路徑",
                    exc,
                )
                return await _instructor_fallback(self._client, self._model, request, messages)
            raise

        usage = response.usage
        choice = response.choices[0]
        if getattr(choice, "finish_reason", None) == "length":
            logger.warning(
                "OpenAI 回應因 max_completion_tokens (%s) 截斷,輸出 %s tokens",
                request.max_output_tokens,
                usage.completion_tokens if usage else None,
            )

        return TextGenerationResult(
            text=choice.message.content or "",
            provider=PROVIDER_OPENAI,
            model=self._model,
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
        )


def _build_messages(request: TextGenerationRequest) -> list[dict]:
    """將 TextGenerationRequest 轉為 OpenAI messages 格式。"""
    messages: list[dict] = []

    if request.system_prompt:
        messages.append({"role": "system", "content": request.system_prompt})

    # 構建 user message
    if request.images:
        from lib.image_backends.base import image_to_base64_data_uri

        content: list[dict] = []
        for img in request.images:
            if img.path:
                data_uri = image_to_base64_data_uri(img.path)
                content.append({"type": "image_url", "image_url": {"url": data_uri}})
            elif img.url:
                content.append({"type": "image_url", "image_url": {"url": img.url}})
        content.append({"type": "text", "text": request.prompt})
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": request.prompt})

    return messages


_SCHEMA_ERROR_KEYWORDS = (
    "response_schema",
    "json_schema",
    "Unknown name",
    "Cannot find field",
    "Invalid JSON payload",
)


def _is_schema_error(exc: BaseException) -> bool:
    """判斷異常是否為 JSON Schema 不相容導致的錯誤。

    除了標準的 400 BadRequestError，一些 OpenAI 相容代理（如 Gemini
    相容端點）會將上游 schema 錯誤包裝成其他狀態碼（如 429），
    因此也檢查錯誤資訊中是否包含 schema 相關關鍵字。
    """
    if isinstance(exc, BadRequestError):
        return True
    # 代理可能把上游 schema 錯誤包裝成非 400 狀態碼
    error_str = str(exc)
    return any(kw in error_str for kw in _SCHEMA_ERROR_KEYWORDS)


async def _instructor_fallback(
    client: AsyncOpenAI,
    model: str,
    request: TextGenerationRequest,
    messages: list[dict],
) -> TextGenerationResult:
    """Instructor 降級：當原生 response_format 不可用時的備選路徑。"""
    from lib.text_backends.instructor_support import instructor_fallback_async

    return await instructor_fallback_async(
        client=client,
        model=model,
        messages=messages,
        response_schema=request.response_schema,
        provider=PROVIDER_OPENAI,
        max_output_tokens=request.max_output_tokens,
    )
