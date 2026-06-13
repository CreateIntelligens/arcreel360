from typing import Any, cast
from unittest.mock import Mock

import pytest
from google.adk.tools.tool_context import ToolContext

from server.agent_runtime.adk_tool_adapters import ALL_TOOLS
from server.agent_runtime.skill_function_declarations import SKILL_DECLARATIONS
from server.agent_runtime.tool_sandbox import FS_LIST_DECLARATION, FS_READ_DECLARATION, FS_WRITE_DECLARATION


def test_tool_declarations_bit_for_bit():
    tools_by_name = {t.name: t for t in ALL_TOOLS}

    def lower_types(d):
        if isinstance(d, dict):
            return {k: (v.lower() if k == "type" and isinstance(v, str) else lower_types(v)) for k, v in d.items()}
        elif isinstance(d, list):
            return [lower_types(i) for i in d]
        return d

    # 驗證 7 個 skill
    for decl in SKILL_DECLARATIONS:
        tool = tools_by_name[decl.name]
        adk_decl = tool._get_declaration()
        assert adk_decl.name == decl.name
        # ADK types.FunctionDeclaration is a pydantic model
        adk_dict = cast(dict[str, Any], lower_types(adk_decl.model_dump(mode="json", exclude_none=True)))
        assert adk_dict["description"] == decl.description
        if "parameters" in adk_dict:
            assert adk_dict["parameters"] == lower_types(decl.parameters)

    # 驗證 IO 工具
    io_decls = [FS_READ_DECLARATION, FS_WRITE_DECLARATION, FS_LIST_DECLARATION]
    for decl in io_decls:
        tool = tools_by_name[decl["name"]]
        adk_decl = tool._get_declaration()
        assert adk_decl.name == decl["name"]
        adk_dict = cast(dict[str, Any], lower_types(adk_decl.model_dump(mode="json", exclude_none=True)))
        assert adk_dict["description"] == decl["description"]
        if "parameters" in adk_dict:
            assert adk_dict["parameters"] == lower_types(decl["parameters"])


@pytest.mark.asyncio
async def test_run_async_dispatch():
    tool_context = Mock(spec=ToolContext)
    tool_context.state = {"skill_ctx": "dummy_ctx"}

    # We will just test that it calls the handler by passing a tool with a dummy handler
    from server.agent_runtime.adk_tool_adapters import SkillBaseTool

    called_ctx = None
    called_args = None

    async def dummy_handler(ctx, args):
        nonlocal called_ctx, called_args
        called_ctx = ctx
        called_args = args
        return {"result": "success"}

    tool = SkillBaseTool(name="dummy", declaration={"name": "dummy", "description": "dummy"}, handler=dummy_handler)
    res = await tool.run_async(args={"foo": "bar"}, tool_context=tool_context)

    assert res == {"result": "success"}
    assert called_ctx == "dummy_ctx"
    assert called_args == {"foo": "bar"}
