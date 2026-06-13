"""文字生成服務層核心介面定義。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol


class TextCapability(StrEnum):
    """文字後端支援的能力列舉。"""

    TEXT_GENERATION = "text_generation"
    STRUCTURED_OUTPUT = "structured_output"
    VISION = "vision"


class TextTaskType(StrEnum):
    """文字生成任務型別。"""

    SCRIPT = "script"
    OVERVIEW = "overview"
    STYLE_ANALYSIS = "style"


@dataclass
class ImageInput:
    """圖片輸入（用於 vision）。"""

    path: Path | None = None
    url: str | None = None


@dataclass
class TextGenerationRequest:
    """通用文字生成請求。各 Backend 忽略不支援的欄位。

    若呼叫端不傳 max_output_tokens,各 backend 走 SDK 預設值（gemini-flash ~8k, openai
    ~16k, byteplus/grok ~4-8k）。長 prompt 任務務必顯式指定，否則容易被悄悄截斷且不報錯。
    """

    prompt: str
    response_schema: dict | type | None = None
    images: list[ImageInput] | None = None
    system_prompt: str | None = None
    max_output_tokens: int | None = None


@dataclass
class TextGenerationResult:
    """通用文字生成結果。"""

    text: str
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


def resolve_schema(schema: dict | type) -> dict:
    """將 response_schema 轉為無 $ref 的純 JSON Schema dict。

    - type (Pydantic 類): 呼叫 model_json_schema() 後內聯 $ref
    - dict: 直接內聯 $ref（如果有）
    """
    if isinstance(schema, type):
        schema = schema.model_json_schema()

    defs = schema.get("$defs", {})
    if not defs:
        return schema

    def _inline(obj, visited_refs=frozenset()):
        if isinstance(obj, dict):
            if "$ref" in obj:
                ref_name = obj["$ref"].split("/")[-1]
                if ref_name in visited_refs:
                    raise ValueError(f"檢測到 schema 中的迴圈引用: {ref_name}")
                resolved = _inline(defs[ref_name], visited_refs | {ref_name})
                extra = {k: v for k, v in obj.items() if k != "$ref"}
                return {**resolved, **extra} if extra else resolved
            return {k: _inline(v, visited_refs) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_inline(item, visited_refs) for item in obj]
        return obj

    result = _inline(schema)
    result.pop("$defs", None)
    return result


class TextBackend(Protocol):
    """文字生成後端協議。"""

    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    @property
    def capabilities(self) -> set[TextCapability]: ...

    async def generate(self, request: TextGenerationRequest) -> TextGenerationResult: ...
