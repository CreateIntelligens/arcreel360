"""Instructor 降級支援 — 為不支援原生結構化輸出的模型提供 prompt 注入 + 解析 + 重試。"""

from __future__ import annotations

import logging

import instructor
from instructor import Mode
from pydantic import BaseModel

from lib.text_backends.base import TextGenerationResult

logger = logging.getLogger(__name__)


def _max_output_token_kwargs(provider: str, max_output_tokens: int | None) -> dict[str, int]:
    if max_output_tokens is None:
        return {}
    key = "max_completion_tokens" if provider == "openai" else "max_tokens"
    return {key: max_output_tokens}


def generate_structured_via_instructor(
    client,
    model: str,
    messages: list[dict],
    response_model: type[BaseModel],
    mode: Mode = Mode.MD_JSON,
    max_retries: int = 2,
    **kwargs,
) -> tuple[str, int | None, int | None]:
    """透過 Instructor 生成結構化輸出（同步版，供 Ark 等同步 SDK 使用）。

    返回 (json_text, input_tokens, output_tokens)。
    """
    patched = instructor.from_openai(client, mode=mode)
    if patched is None:
        raise TypeError(
            f"instructor.from_openai() 返回 None — client 型別 {type(client).__name__} 不受支援，"
            "請傳入 openai.OpenAI 或 openai.AsyncOpenAI 例項"
        )
    result, completion = patched.chat.completions.create_with_completion(
        model=model,
        messages=messages,
        response_model=response_model,
        max_retries=max_retries,
        **kwargs,
    )
    json_text = result.model_dump_json()

    choices = getattr(completion, "choices", None)
    if choices and getattr(choices[0], "finish_reason", None) == "length":
        limit = kwargs.get("max_completion_tokens") or kwargs.get("max_tokens")
        logger.warning("Instructor 同步回應因 %s 限制而截斷", limit)

    input_tokens = None
    output_tokens = None
    if completion.usage:
        input_tokens = completion.usage.prompt_tokens
        output_tokens = completion.usage.completion_tokens

    return json_text, input_tokens, output_tokens


async def generate_structured_via_instructor_async(
    client,
    model: str,
    messages: list[dict],
    response_model: type[BaseModel],
    mode: Mode = Mode.MD_JSON,
    max_retries: int = 2,
    **kwargs,
) -> tuple[str, int | None, int | None]:
    """透過 Instructor 生成結構化輸出（非同步版，供 OpenAI AsyncOpenAI 使用）。

    返回 (json_text, input_tokens, output_tokens)。
    """
    patched = instructor.from_openai(client, mode=mode)
    if patched is None:
        raise TypeError(
            f"instructor.from_openai() 返回 None — client 型別 {type(client).__name__} 不受支援，"
            "請傳入 openai.OpenAI 或 openai.AsyncOpenAI 例項"
        )
    result, completion = await patched.chat.completions.create_with_completion(
        model=model,
        messages=messages,
        response_model=response_model,
        max_retries=max_retries,
        **kwargs,
    )
    json_text = result.model_dump_json()

    choices = getattr(completion, "choices", None)
    if choices and getattr(choices[0], "finish_reason", None) == "length":
        limit = kwargs.get("max_completion_tokens") or kwargs.get("max_tokens")
        logger.warning("Instructor 非同步回應因 %s 限制而截斷", limit)

    input_tokens = None
    output_tokens = None
    if completion.usage:
        input_tokens = completion.usage.prompt_tokens
        output_tokens = completion.usage.completion_tokens

    return json_text, input_tokens, output_tokens


def inject_json_instruction(messages: list[dict]) -> list[dict]:
    """向 messages 注入 JSON 格式指令，確保 json_object 模式可用。

    OpenAI API 要求 prompt 中包含 "JSON" 關鍵字才能啟用 json_object 模式。
    若 messages 中已包含 "JSON"，則原樣返回副本。
    """
    fb_messages = list(messages)
    if any("JSON" in (m.get("content") or "") for m in fb_messages):
        return fb_messages
    sys_idx = next((i for i, m in enumerate(fb_messages) if m.get("role") == "system"), None)
    if sys_idx is not None:
        orig = fb_messages[sys_idx]
        fb_messages[sys_idx] = {**orig, "content": (orig.get("content") or "") + "\nRespond in JSON format."}
    else:
        fb_messages.insert(0, {"role": "system", "content": "Respond in JSON format."})
    return fb_messages


def instructor_fallback_sync(
    client,
    model: str,
    messages: list[dict],
    response_schema: dict | type,
    provider: str,
    max_output_tokens: int | None = None,
):
    """同步 Instructor 降級路徑。

    - response_schema 為 Pydantic 類 → instructor create_with_completion
    - response_schema 為 dict → inject JSON instruction + json_object 模式

    供 Ark 等同步 SDK 後端使用（呼叫方用 asyncio.to_thread 包裝）。
    不做重試，瞬態錯誤由呼叫方的重試迴圈統一處理。
    """
    extra_kwargs = _max_output_token_kwargs(provider, max_output_tokens)

    if isinstance(response_schema, type):
        json_text, input_tokens, output_tokens = generate_structured_via_instructor(
            client=client,
            model=model,
            messages=messages,
            response_model=response_schema,
            **extra_kwargs,
        )
        return TextGenerationResult(
            text=json_text,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    logger.info("response_schema 為 dict，無法使用 Instructor，回退到 json_object 模式")
    fb_messages = inject_json_instruction(messages)
    response = client.chat.completions.create(
        model=model,
        messages=fb_messages,
        response_format={"type": "json_object"},
        **extra_kwargs,
    )
    usage = getattr(response, "usage", None)
    choice = response.choices[0]
    if getattr(choice, "finish_reason", None) == "length":
        logger.warning("JSON Object 同步 fallback 回應被截斷 (%s), 輸出限制: %s", provider, max_output_tokens)
    text = choice.message.content or ""
    return TextGenerationResult(
        text=text.strip() if isinstance(text, str) else str(text),
        provider=provider,
        model=model,
        input_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
        output_tokens=getattr(usage, "completion_tokens", None) if usage else None,
    )


async def instructor_fallback_async(
    client,
    model: str,
    messages: list[dict],
    response_schema: dict | type,
    provider: str,
    max_output_tokens: int | None = None,
):
    """非同步 Instructor 降級路徑。

    - response_schema 為 Pydantic 類 → instructor create_with_completion (async)
    - response_schema 為 dict → inject JSON instruction + json_object 模式 (async)

    供 OpenAI 等原生非同步 SDK 後端使用。
    不做重試，瞬態錯誤由呼叫方的重試迴圈統一處理。
    """
    extra_kwargs = _max_output_token_kwargs(provider, max_output_tokens)

    if isinstance(response_schema, type):
        json_text, input_tokens, output_tokens = await generate_structured_via_instructor_async(
            client=client,
            model=model,
            messages=messages,
            response_model=response_schema,
            **extra_kwargs,
        )
        return TextGenerationResult(
            text=json_text,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    logger.info("response_schema 為 dict，無法使用 Instructor，回退到 json_object 模式")
    fb_messages = inject_json_instruction(messages)
    response = await client.chat.completions.create(
        model=model,
        messages=fb_messages,
        response_format={"type": "json_object"},
        **extra_kwargs,
    )
    usage = getattr(response, "usage", None)
    choice = response.choices[0]
    if getattr(choice, "finish_reason", None) == "length":
        logger.warning("JSON Object 非同步 fallback 回應被截斷 (%s), 輸出限制: %s", provider, max_output_tokens)
    text = choice.message.content or ""
    return TextGenerationResult(
        text=text.strip() if isinstance(text, str) else str(text),
        provider=provider,
        model=model,
        input_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
        output_tokens=getattr(usage, "completion_tokens", None) if usage else None,
    )
