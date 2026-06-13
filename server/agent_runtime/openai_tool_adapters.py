"""OpenAI Agents SDK tool adapters for ArcReel assistant skills."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from agents import FunctionTool
from agents.tool_context import ToolContext

from server.agent_runtime.permission_gate import PermissionGate, as_openai_wrapper
from server.agent_runtime.skill_function_declarations import (
    SKILL_DECLARATIONS,
    SKILL_HANDLERS,
    FunctionDeclaration,
    SkillCallContext,
    SkillHandler,
    get_skill_names,
    run_subagent,
)
from server.agent_runtime.tool_sandbox import (
    FS_LIST_DECLARATION as _FS_LIST_DECL_DICT,
)
from server.agent_runtime.tool_sandbox import (
    FS_READ_DECLARATION as _FS_READ_DECL_DICT,
)
from server.agent_runtime.tool_sandbox import (
    FS_WRITE_DECLARATION as _FS_WRITE_DECL_DICT,
)
from server.agent_runtime.tool_sandbox import (
    fs_list_handler,
    fs_read_handler,
    fs_write_handler,
)

OpenAIToolHandler = Callable[[SkillCallContext, dict[str, Any]], Awaitable[dict[str, Any]]]


# tool_sandbox 中的 dict 形式宣告是中性真相源(ADK 直接吃 dict);這裡包成
# pydantic FunctionDeclaration 給 OpenAI Agents SDK 用,避免兩處寫死字串。
FS_READ_DECLARATION = FunctionDeclaration(**_FS_READ_DECL_DICT)
FS_WRITE_DECLARATION = FunctionDeclaration(**_FS_WRITE_DECL_DICT)
FS_LIST_DECLARATION = FunctionDeclaration(**_FS_LIST_DECL_DICT)

RUN_SUBAGENT_DECLARATION = FunctionDeclaration(
    name="run_subagent",
    description="依 skill 名稱同步 dispatch 一個 ArcReel skill。通常優先直接呼叫同名 skill 工具。",
    parameters={
        "type": "object",
        "properties": {
            "skill": {
                "type": "string",
                "enum": get_skill_names(),
                "description": "要執行的 skill 名稱",
            },
            "args": {
                "type": "object",
                "description": "傳給該 skill 的 JSON 參數",
                "additionalProperties": True,
            },
        },
        "required": ["skill", "args"],
    },
)

OPENAI_TOOL_DECLARATIONS: list[FunctionDeclaration] = [
    FS_READ_DECLARATION,
    FS_WRITE_DECLARATION,
    FS_LIST_DECLARATION,
    RUN_SUBAGENT_DECLARATION,
    *SKILL_DECLARATIONS,
]


async def _handle_run_subagent(ctx: SkillCallContext, args: dict[str, Any]) -> dict[str, Any]:
    skill = str(args.get("skill") or "")
    skill_args = args.get("args")
    return await run_subagent(ctx, skill, skill_args if isinstance(skill_args, dict) else {})


OPENAI_TOOL_HANDLERS: dict[str, OpenAIToolHandler] = {
    **SKILL_HANDLERS,
    "fs_read": fs_read_handler,
    "fs_write": fs_write_handler,
    "fs_list": fs_list_handler,
    "run_subagent": _handle_run_subagent,
}


def _normalize_json_schema_type(value: Any) -> Any:
    if isinstance(value, str):
        return value.lower()
    name = getattr(value, "name", None)
    if isinstance(name, str):
        return name.lower()
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str):
        return enum_value.lower()
    return value


def _convert_schema_node(value: Any) -> Any:
    if isinstance(value, list):
        return [_convert_schema_node(item) for item in value]
    if not isinstance(value, Mapping):
        return _normalize_json_schema_type(value)

    converted: dict[str, Any] = {}
    for key, child in value.items():
        converted[key] = _normalize_json_schema_type(child) if key == "type" else _convert_schema_node(child)

    if converted.get("type") == "object":
        converted["additionalProperties"] = False
        properties = converted.get("properties")
        if not isinstance(properties, dict):
            properties = {}
            converted["properties"] = properties
        converted["required"] = list(properties.keys())
    return converted


def _gemini_to_openai_schema(parameters: dict[str, Any]) -> dict[str, Any]:
    """把 Gemini FunctionDeclaration parameters 轉為 OpenAI strict JSON Schema。

    `_convert_schema_node` 已建立全新 dict / list 結構,不需先 deepcopy。
    """

    return _convert_schema_node(parameters)


def _parse_tool_args(raw_args: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw_args, dict):
        return raw_args
    try:
        decoded = json.loads(raw_args or "{}")
    except json.JSONDecodeError as exc:
        return {"_parse_error": str(exc)}
    return decoded if isinstance(decoded, dict) else {"_invalid_args": decoded}


def build_skill_tools(
    declarations: list[FunctionDeclaration],
    handlers: dict[str, SkillHandler | OpenAIToolHandler],
    gate: PermissionGate,
) -> list[FunctionTool]:
    """把 ArcReel FunctionDeclaration + handler registry 包成 OpenAI FunctionTool."""

    tools: list[FunctionTool] = []
    for declaration in declarations:
        handler = handlers[declaration.name]
        wrapped = as_openai_wrapper(gate, declaration.name)(handler)

        async def on_invoke_tool(
            ctx: ToolContext[Any],
            raw_args: str,
            _wrapped: OpenAIToolHandler = wrapped,
        ) -> dict[str, Any]:
            args = _parse_tool_args(raw_args)
            if "_parse_error" in args:
                return {"error": "invalid_json", "reason": args["_parse_error"]}
            if "_invalid_args" in args:
                return {"error": "invalid_argument", "reason": "tool arguments must be a JSON object"}
            return await _wrapped(ctx, args)

        tools.append(
            FunctionTool(
                name=declaration.name,
                description=declaration.description,
                params_json_schema=_gemini_to_openai_schema(declaration.parameters),
                on_invoke_tool=on_invoke_tool,
                strict_json_schema=True,
            )
        )
    return tools
