"""ADK Tool adapters for ArcReel skills."""

from collections.abc import Awaitable, Callable
from typing import Any

from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from server.agent_runtime.skill_function_declarations import (
    SKILL_DECLARATIONS,
    SKILL_HANDLERS,
    FunctionDeclaration,
    SkillCallContext,
)
from server.agent_runtime.tool_sandbox import (
    FS_LIST_DECLARATION,
    FS_READ_DECLARATION,
    FS_WRITE_DECLARATION,
    fs_list_handler,
    fs_read_handler,
    fs_write_handler,
)

HandlerType = Callable[[SkillCallContext, dict[str, Any]], Awaitable[dict[str, Any]]]


class SkillBaseTool(BaseTool):
    def __init__(
        self,
        name: str,
        declaration: dict[str, Any] | FunctionDeclaration,
        handler: HandlerType,
        requires_permission: bool = False,
    ):
        if isinstance(declaration, FunctionDeclaration):
            desc = declaration.description
            self._decl_dict = declaration.to_gemini()
        else:
            desc = declaration.get("description", "")
            self._decl_dict = declaration

        super().__init__(name=name, description=desc)
        self._handler = handler
        self._requires_permission = requires_permission
        # 禁止 ADK 從 Python signature 自動推導:cache 一次,避免每次 LLM
        # planning 都重建 FunctionDeclaration。
        self._cached_declaration = types.FunctionDeclaration(
            name=self._decl_dict["name"],
            description=self._decl_dict.get("description"),
            parameters=self._decl_dict.get("parameters"),
        )

    def _get_declaration(self) -> types.FunctionDeclaration | None:
        return self._cached_declaration

    async def run_async(self, *, args: dict[str, Any], tool_context: ToolContext) -> Any:
        # ADK ToolContext 的 state 是直接的 dict-like 屬性,沒有 .session 巢層
        skill_ctx: SkillCallContext = tool_context.state.get("skill_ctx")
        if not skill_ctx:
            raise RuntimeError("skill_ctx missing in tool_context.state")
        return await self._handler(skill_ctx, args)


def _build_skill_tools() -> list[SkillBaseTool]:
    tools: list[SkillBaseTool] = []
    for decl in SKILL_DECLARATIONS:
        tools.append(SkillBaseTool(name=decl.name, declaration=decl, handler=SKILL_HANDLERS[decl.name]))
    tools.append(SkillBaseTool(name="fs_read", declaration=FS_READ_DECLARATION, handler=fs_read_handler))
    tools.append(SkillBaseTool(name="fs_write", declaration=FS_WRITE_DECLARATION, handler=fs_write_handler))
    tools.append(SkillBaseTool(name="fs_list", declaration=FS_LIST_DECLARATION, handler=fs_list_handler))
    return tools


ALL_TOOLS = _build_skill_tools()
