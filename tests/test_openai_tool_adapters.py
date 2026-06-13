"""OpenAI Agents SDK tool adapter tests."""

from __future__ import annotations

import json
from dataclasses import replace
from enum import Enum
from pathlib import Path
from typing import Any

import pytest
from agents import Agent, FunctionTool, RunConfig, Runner
from agents.items import ModelResponse, ToolCallOutputItem
from agents.model_settings import ModelSettings
from agents.models.interface import Model, ModelTracing
from agents.tool_context import ToolContext
from agents.usage import Usage
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText

from lib.project_manager import ProjectManager
from server.agent_runtime.permission_gate import AlwaysAllowGate, CallableGate, Deny
from server.agent_runtime.skill_function_declarations import (
    SKILL_HANDLERS,
    FunctionDeclaration,
    SkillCallContext,
)
from server.agent_runtime.tool_sandbox import ToolSandbox


class _ToolCallThenMessageModel(Model):
    def __init__(self) -> None:
        self.inputs: list[Any] = []

    async def get_response(
        self,
        system_instructions: str | None,
        input: str | list[Any],
        model_settings: ModelSettings,
        tools: list[Any],
        output_schema: Any,
        handoffs: list[Any],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        prompt: Any,
    ) -> ModelResponse:
        self.inputs.append(input)
        if len(self.inputs) == 1:
            return ModelResponse(
                output=[
                    ResponseFunctionToolCall(
                        id="fc_1",
                        call_id="call_1",
                        name="fs_write",
                        arguments=json.dumps({"path": "scripts/x.json", "content": "blocked"}),
                        status="completed",
                        type="function_call",
                    )
                ],
                usage=Usage(),
                response_id="resp_1",
            )
        return ModelResponse(
            output=[
                ResponseOutputMessage(
                    id="msg_1",
                    content=[ResponseOutputText(annotations=[], text="我已改用其他方式。", type="output_text")],
                    role="assistant",
                    status="completed",
                    type="message",
                )
            ],
            usage=Usage(),
            response_id="resp_2",
        )

    async def stream_response(self, *_args: Any, **_kwargs: Any):  # type: ignore[no-untyped-def]
        raise NotImplementedError


class _GeminiType(Enum):
    OBJECT = "OBJECT"
    ARRAY = "ARRAY"
    STRING = "STRING"


@pytest.fixture
def skill_context(tmp_path: Path) -> SkillCallContext:
    project_root = tmp_path / "projects"
    project_name = "demo"
    (project_root / project_name / "source").mkdir(parents=True)
    manager = ProjectManager(projects_root=str(project_root))
    return SkillCallContext(
        project_name=project_name,
        sandbox=ToolSandbox(project_root=project_root, project_name=project_name),
        project_manager=manager,
        session_id="openai-full:abc123",
    )


def test_gemini_schema_is_converted_to_openai_strict_json_schema() -> None:
    from server.agent_runtime.openai_tool_adapters import _gemini_to_openai_schema

    source = {
        "type": _GeminiType.OBJECT,
        "properties": {
            "items": {
                "type": _GeminiType.ARRAY,
                "items": {
                    "type": _GeminiType.OBJECT,
                    "properties": {
                        "name": {"type": _GeminiType.STRING},
                    },
                },
            },
        },
        "required": ["items"],
    }

    converted = _gemini_to_openai_schema(source)

    assert converted == {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                    },
                    "required": ["name"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["items"],
        "additionalProperties": False,
    }
    assert "additionalProperties" not in source


def test_openai_tool_declarations_cover_skills_and_fs_tools() -> None:
    from server.agent_runtime.openai_tool_adapters import OPENAI_TOOL_DECLARATIONS

    names = {decl.name for decl in OPENAI_TOOL_DECLARATIONS}
    assert names == {
        *SKILL_HANDLERS.keys(),
        "fs_read",
        "fs_write",
        "fs_list",
        "run_subagent",
    }
    assert len(OPENAI_TOOL_DECLARATIONS) == len(SKILL_HANDLERS) + 4


def test_each_openai_tool_schema_is_strict_object_schema() -> None:
    from server.agent_runtime.openai_tool_adapters import OPENAI_TOOL_DECLARATIONS, _gemini_to_openai_schema

    def assert_strict_types(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                assert_strict_types(item)
            return
        if not isinstance(node, dict):
            return
        if "type" in node:
            assert isinstance(node["type"], str)
            assert node["type"] == node["type"].lower()
        if node.get("type") == "object":
            assert node["additionalProperties"] is False
        if node.get("type") == "object" and isinstance(node.get("properties"), dict):
            assert set(node["required"]) == set(node["properties"])
        for child in node.values():
            assert_strict_types(child)

    for declaration in OPENAI_TOOL_DECLARATIONS:
        schema = _gemini_to_openai_schema(declaration.parameters)
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert_strict_types(schema)


@pytest.mark.asyncio
async def test_build_skill_tools_wraps_handlers_as_function_tools(skill_context: SkillCallContext) -> None:
    from server.agent_runtime.openai_tool_adapters import build_skill_tools

    called: dict[str, Any] = {}

    async def handler(ctx: SkillCallContext, args: dict[str, Any]) -> dict[str, Any]:
        called["ctx"] = ctx
        called["args"] = args
        return {"ok": True, "episode": args["episode"], "session_id": ctx.session_id}

    declaration = FunctionDeclaration(
        name="demo_tool",
        description="Demo tool",
        parameters={
            "type": "object",
            "properties": {"episode": {"type": "integer"}},
            "required": ["episode"],
        },
    )

    tools = build_skill_tools([declaration], {"demo_tool": handler}, AlwaysAllowGate())

    assert len(tools) == 1
    tool = tools[0]
    assert isinstance(tool, FunctionTool)
    assert tool.name == "demo_tool"
    assert tool.description == "Demo tool"
    assert tool.strict_json_schema is True
    assert tool.params_json_schema["additionalProperties"] is False

    result = await tool.on_invoke_tool(ToolContext(skill_context, tool_call_id="call-demo"), json.dumps({"episode": 3}))

    assert result == {"ok": True, "episode": 3, "session_id": "openai-full:abc123"}
    assert called == {"ctx": skill_context, "args": {"episode": 3}}


@pytest.mark.asyncio
async def test_media_tool_waits_for_button_approval_before_running(skill_context: SkillCallContext) -> None:
    from server.agent_runtime.openai_tool_adapters import build_skill_tools

    approvals: list[dict[str, Any]] = []
    called: dict[str, Any] = {}

    async def approval_requester(payload: dict[str, Any]) -> dict[str, str]:
        approvals.append(payload)
        question = payload["questions"][0]["question"]
        return {question: "確認生成"}

    approved_context = replace(skill_context, approval_requester=approval_requester)

    async def handler(ctx: SkillCallContext, args: dict[str, Any]) -> dict[str, Any]:
        called["ctx"] = ctx
        called["args"] = args
        return {"ok": True, "episode": args["episode"]}

    declaration = FunctionDeclaration(
        name="generate_video",
        description="Generate video",
        parameters={
            "type": "object",
            "properties": {"episode": {"type": "integer"}},
            "required": ["episode"],
        },
    )

    tool = build_skill_tools([declaration], {"generate_video": handler}, AlwaysAllowGate())[0]
    result = await tool.on_invoke_tool(
        ToolContext(approved_context, tool_call_id="call-video"),
        json.dumps({"episode": 2}),
    )

    assert result == {"ok": True, "episode": 2}
    assert called == {"ctx": approved_context, "args": {"episode": 2}}
    assert len(approvals) == 1
    question = approvals[0]["questions"][0]
    assert approvals[0]["type"] == "ask_user_question"
    assert approvals[0]["question_id"].startswith("approval_")
    assert question == {
        "header": "確認",
        "question": "確定要開始生成第 2 集的影片嗎？",
        "options": [
            {"label": "確認生成", "description": "開始執行這個生成任務"},
            {"label": "取消", "description": "不要執行這個生成任務"},
        ],
        "multiSelect": False,
        "allowOther": False,
    }


@pytest.mark.asyncio
async def test_media_tool_cancelled_by_button_does_not_run_handler(skill_context: SkillCallContext) -> None:
    from server.agent_runtime.openai_tool_adapters import build_skill_tools

    async def approval_requester(payload: dict[str, Any]) -> dict[str, str]:
        question = payload["questions"][0]["question"]
        return {question: "取消"}

    cancelled_context = replace(skill_context, approval_requester=approval_requester)
    handler_called = False

    async def handler(_ctx: SkillCallContext, _args: dict[str, Any]) -> dict[str, Any]:
        nonlocal handler_called
        handler_called = True
        return {"ok": True}

    declaration = FunctionDeclaration(
        name="generate_storyboard",
        description="Generate storyboard",
        parameters={
            "type": "object",
            "properties": {"episode": {"type": "integer"}},
            "required": ["episode"],
        },
    )

    tool = build_skill_tools([declaration], {"generate_storyboard": handler}, AlwaysAllowGate())[0]
    result = await tool.on_invoke_tool(
        ToolContext(cancelled_context, tool_call_id="call-storyboard"),
        json.dumps({"episode": 1}),
    )

    assert handler_called is False
    assert result == {
        "permission_denied": True,
        "reason": "user_cancelled",
        "question": "確定要開始生成第 1 集的分鏡圖嗎？",
        "tool": "generate_storyboard",
    }


@pytest.mark.asyncio
async def test_built_fs_read_tool_calls_sandbox(skill_context: SkillCallContext) -> None:
    from server.agent_runtime.openai_tool_adapters import (
        OPENAI_TOOL_DECLARATIONS,
        OPENAI_TOOL_HANDLERS,
        build_skill_tools,
    )

    source_file = skill_context.sandbox.allowed_root / "source" / "chapter1.txt"
    source_file.write_text("hello", encoding="utf-8")

    tools = build_skill_tools(OPENAI_TOOL_DECLARATIONS, OPENAI_TOOL_HANDLERS, AlwaysAllowGate())
    fs_read_tool = next(tool for tool in tools if tool.name == "fs_read")

    result = await fs_read_tool.on_invoke_tool(
        ToolContext(skill_context, tool_call_id="call-fs-read"),
        json.dumps({"path": "source/chapter1.txt"}),
    )

    assert result == {"content": "hello", "bytes_read": 5, "truncated": False}


@pytest.mark.asyncio
async def test_runner_receives_permission_deny_as_tool_result(skill_context: SkillCallContext) -> None:
    from server.agent_runtime.openai_tool_adapters import OPENAI_TOOL_DECLARATIONS, build_skill_tools

    handler_called = False

    async def fs_write_handler(_ctx: SkillCallContext, _args: dict[str, Any]) -> dict[str, Any]:
        nonlocal handler_called
        handler_called = True
        return {"ok": True}

    handlers = {declaration.name: fs_write_handler for declaration in OPENAI_TOOL_DECLARATIONS}
    fake_model = _ToolCallThenMessageModel()
    agent = Agent(
        name="deny-test",
        instructions="test",
        model=fake_model,
        tools=build_skill_tools(
            OPENAI_TOOL_DECLARATIONS,
            handlers,
            CallableGate(lambda *_args: Deny("user rejected")),
        ),
    )

    result = await Runner.run(
        agent,
        input="write a file",
        context=skill_context,
        max_turns=3,
        run_config=RunConfig(tracing_disabled=True),
    )

    assert handler_called is False
    tool_outputs = [item for item in result.new_items if isinstance(item, ToolCallOutputItem)]
    assert len(tool_outputs) == 1
    assert tool_outputs[0].output == {
        "permission_denied": True,
        "reason": "user rejected",
        "tool": "fs_write",
    }
    second_model_input = fake_model.inputs[1]
    function_outputs = [item for item in second_model_input if item.get("type") == "function_call_output"]
    assert function_outputs == [
        {
            "call_id": "call_1",
            "output": "{'permission_denied': True, 'reason': 'user rejected', 'tool': 'fs_write'}",
            "type": "function_call_output",
        }
    ]


@pytest.mark.asyncio
async def test_always_allow_gate_asks_user_for_destructive_actions() -> None:
    from server.agent_runtime.permission_gate import Allow, AlwaysAllowGate, AskUser

    gate = AlwaysAllowGate()

    decision_delete = gate.check("delete_entity", {"entity_type": "character", "name": "小明"}, "session_123")
    assert isinstance(decision_delete, AskUser)
    assert decision_delete.question == "確定要刪除專案中的角色「小明」嗎？"

    decision_rename = gate.check(
        "rename_entity", {"entity_type": "clue", "old_name": "舊道具", "new_name": "新道具"}, "session_123"
    )
    assert isinstance(decision_rename, AskUser)
    assert decision_rename.question == "確定要將專案中的道具「舊道具」改名為「新道具」嗎？"

    decision_other = gate.check("fs_read", {"path": "x.json"}, "session_123")
    assert isinstance(decision_other, Allow)


@pytest.mark.asyncio
async def test_destructive_openai_tool_returns_approval_required(skill_context: SkillCallContext) -> None:
    from server.agent_runtime.openai_tool_adapters import build_skill_tools

    handler_called = False

    async def delete_handler(_ctx: SkillCallContext, _args: dict[str, Any]) -> dict[str, Any]:
        nonlocal handler_called
        handler_called = True
        return {"ok": True}

    declaration = FunctionDeclaration(
        name="delete_entity",
        description="Delete entity",
        parameters={
            "type": "object",
            "properties": {
                "entity_type": {"type": "string"},
                "name": {"type": "string"},
            },
            "required": ["entity_type", "name"],
        },
    )

    tool = build_skill_tools([declaration], {"delete_entity": delete_handler}, AlwaysAllowGate())[0]
    result = await tool.on_invoke_tool(
        ToolContext(skill_context, tool_call_id="call-delete"),
        json.dumps({"entity_type": "scene", "name": "雨夜街口"}),
    )

    assert handler_called is False
    assert result == {
        "permission_denied": True,
        "reason": "approval_required",
        "question": "確定要刪除專案中的場景「雨夜街口」嗎？",
        "tool": "delete_entity",
    }
