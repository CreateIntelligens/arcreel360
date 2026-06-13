"""PreToolUse 风格的权限闸门。

每次工具执行前由 provider 调用 ``gate.check(tool_name, args, session_id)``，
返回 ``Allow`` / ``Deny`` / ``AskUser``。默认 ``AlwaysAllowGate`` 放行非破壞性操作，
但對改名/刪除等破壞性操作要求人工確認；未來可掛載自定義實作（如前端 modal 審批）而
無需改 provider。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol
from uuid import uuid4


@dataclass(frozen=True)
class Allow:
    pass


@dataclass(frozen=True)
class Deny:
    reason: str


@dataclass(frozen=True)
class AskUser:
    """请求人工审批；内含给前端展示的问题。

    ``kind`` 区分审批语意（generate=生成任务 / execute=一般操作），决定确认
    按钮的措辞，避免从 ``question`` 文案反推语意。
    """

    question: str
    kind: Literal["generate", "execute"] = "execute"


_ENTITY_LABELS: dict[str, str] = {
    "character": "角色",
    "clue": "道具",
    "scene": "場景",
}

_MEDIA_GENERATION_LABELS: dict[str, str] = {
    "generate_storyboard": "分鏡圖",
    "generate_video": "影片",
    "generate_character_sheets": "角色設計圖",
    "generate_clue_sheets": "道具設計圖",
    "generate_scene_sheets": "場景設計圖",
}

PermissionDecision = Allow | Deny | AskUser
GateCallable = Callable[[str, dict[str, Any], str], PermissionDecision | bool | str | None]
OpenAIToolHandler = Callable[[Any, dict[str, Any]], Awaitable[dict[str, Any]]]

_APPROVAL_CONFIRM_GENERATE_LABEL = "確認生成"
_APPROVAL_CONFIRM_EXECUTE_LABEL = "確認執行"
_APPROVAL_CANCEL_LABEL = "取消"


class PermissionGate(Protocol):
    """权限闸门协议。

    实现类应是无状态的，或自行管理状态。返回 ``Deny`` 时不抛异常，
    由调用方把 ``reason`` 塞进 ``functionResponse`` 反馈给模型。
    """

    def check(
        self,
        tool_name: str,
        args: dict[str, Any],
        session_id: str,
    ) -> PermissionDecision: ...


class AlwaysAllowGate:
    """默认放行非破壞性请求，改名/删除需要人工确认。

    适用于无审批 UI 的部署，或测试环境。
    """

    def check(
        self,
        tool_name: str,
        args: dict[str, Any],
        session_id: str,
    ) -> PermissionDecision:
        effective_tool_name, effective_args = _resolve_effective_tool(tool_name, args)
        if effective_tool_name in _MEDIA_GENERATION_LABELS:
            return AskUser(
                question=_build_media_generation_question(effective_tool_name, effective_args),
                kind="generate",
            )
        if tool_name == "delete_entity":
            entity_type = args.get("entity_type", "entity")
            label = _ENTITY_LABELS.get(str(entity_type), "實體")
            name = args.get("name", "")
            return AskUser(question=f"確定要刪除專案中的{label}「{name}」嗎？")
        if tool_name == "rename_entity":
            entity_type = args.get("entity_type", "entity")
            label = _ENTITY_LABELS.get(str(entity_type), "實體")
            old_name = args.get("old_name", "")
            new_name = args.get("new_name", "")
            return AskUser(question=f"確定要將專案中的{label}「{old_name}」改名為「{new_name}」嗎？")
        return Allow()


def _resolve_effective_tool(tool_name: str, args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if tool_name != "run_subagent":
        return tool_name, args

    skill_name = str(args.get("skill") or "")
    skill_args = args.get("args")
    return skill_name, skill_args if isinstance(skill_args, dict) else {}


def _format_episode(args: dict[str, Any]) -> str:
    episode = args.get("episode")
    return f"第 {episode} 集" if isinstance(episode, int) and episode >= 1 else "目前劇集"


def _format_media_scope(args: dict[str, Any]) -> str:
    scene_ids = args.get("scene_ids")
    if isinstance(scene_ids, list) and scene_ids:
        return f"的 {len(scene_ids)} 個指定分鏡"
    return ""


def _build_media_generation_question(tool_name: str, args: dict[str, Any]) -> str:
    media_label = _MEDIA_GENERATION_LABELS[tool_name]
    names = args.get("names")
    if isinstance(names, list) and names:
        return f"確定要開始生成 {len(names)} 個指定{media_label}嗎？"
    if tool_name in {"generate_character_sheets", "generate_clue_sheets", "generate_scene_sheets"}:
        return f"確定要開始生成所有缺少的{media_label}嗎？"
    scope = _format_media_scope(args)
    if scope:
        return f"確定要開始生成{_format_episode(args)}{scope}{media_label}嗎？"
    return f"確定要開始生成{_format_episode(args)}的{media_label}嗎？"


class CallableGate:
    """把任意可调用对象包装成 ``PermissionGate``。

    用于运行时挂载自定义逻辑（例如把前端审批结果接入）。
    """

    def __init__(self, fn: GateCallable):
        self._fn = fn

    def check(
        self,
        tool_name: str,
        args: dict[str, Any],
        session_id: str,
    ) -> PermissionDecision:
        result = self._fn(tool_name, args, session_id)
        if isinstance(result, (Allow, Deny, AskUser)):
            return result
        # 容错：把简单返回值映射到决策
        if result is True or result is None:
            return Allow()
        if result is False:
            return Deny("rejected")
        if isinstance(result, str):
            return Deny(result)
        raise TypeError(f"gate callable returned unsupported type: {type(result).__name__}")


# 默认全局 gate 实例。Provider 启动时持有此引用；
# 如需自定义，可在 service 层用 ``set_default_gate`` 替换。
_default_gate: PermissionGate = AlwaysAllowGate()


def get_default_gate() -> PermissionGate:
    return _default_gate


def set_default_gate(gate: PermissionGate) -> None:
    global _default_gate
    _default_gate = gate


def _session_id_from_openai_context(ctx: Any) -> str:
    handler_context = getattr(ctx, "context", ctx)
    session_id = getattr(handler_context, "session_id", None) or getattr(ctx, "session_id", None)
    return str(session_id or "")


def _handler_context_from_openai_context(ctx: Any) -> Any:
    return getattr(ctx, "context", ctx)


def _approval_requester_from_context(ctx: Any) -> Callable[[dict[str, Any]], Awaitable[dict[str, str]]] | None:
    requester = getattr(ctx, "approval_requester", None)
    if callable(requester):
        return requester
    return None


def _adk_handler_context(tool_context: Any) -> Any:
    state = getattr(tool_context, "state", None)
    if isinstance(state, dict):
        return state.get("skill_ctx")
    return None


def _decision_to_denied_payload(decision: PermissionDecision, tool_name: str) -> dict[str, Any] | None:
    """把 PermissionGate 的 decision 轉成 canonical denied dict;Allow 回 None。

    所有 SDK adapter 都呼叫這個 helper,確保 deny payload 跨 provider 1:1 對齊。
    """
    if isinstance(decision, Allow):
        return None
    if isinstance(decision, Deny):
        return {
            "permission_denied": True,
            "reason": decision.reason,
            "tool": tool_name,
        }
    if isinstance(decision, AskUser):
        return {
            "permission_denied": True,
            "reason": "approval_required",
            "question": decision.question,
            "tool": tool_name,
        }
    return {
        "permission_denied": True,
        "reason": "unknown_permission_decision",
        "tool": tool_name,
    }


def _approval_confirm_label(decision: AskUser) -> str:
    return _APPROVAL_CONFIRM_GENERATE_LABEL if decision.kind == "generate" else _APPROVAL_CONFIRM_EXECUTE_LABEL


def _build_approval_payload(decision: AskUser) -> dict[str, Any]:
    is_generate = decision.kind == "generate"
    confirm_label = _APPROVAL_CONFIRM_GENERATE_LABEL if is_generate else _APPROVAL_CONFIRM_EXECUTE_LABEL
    confirm_desc = "開始執行這個生成任務" if is_generate else "執行這個操作"
    cancel_desc = "不要執行這個生成任務" if is_generate else "不要執行這個操作"
    return {
        "type": "ask_user_question",
        "question_id": f"approval_{uuid4().hex}",
        "questions": [
            {
                "header": "確認",
                "question": decision.question,
                "options": [
                    {"label": confirm_label, "description": confirm_desc},
                    {"label": _APPROVAL_CANCEL_LABEL, "description": cancel_desc},
                ],
                "multiSelect": False,
                "allowOther": False,
            }
        ],
    }


async def _resolve_ask_user_decision(
    decision: AskUser,
    tool_name: str,
    handler_context: Any,
) -> dict[str, Any] | None:
    requester = _approval_requester_from_context(handler_context)
    if requester is None:
        return _decision_to_denied_payload(decision, tool_name)

    try:
        answers = await requester(_build_approval_payload(decision))
    except Exception as exc:
        return {
            "permission_denied": True,
            "reason": "approval_failed",
            "question": decision.question,
            "tool": tool_name,
            "error": str(exc),
        }

    if answers.get(decision.question) == _approval_confirm_label(decision):
        return None
    return {
        "permission_denied": True,
        "reason": "user_cancelled",
        "question": decision.question,
        "tool": tool_name,
    }


def as_openai_wrapper(
    gate: PermissionGate,
    tool_name: str,
) -> Callable[[OpenAIToolHandler], OpenAIToolHandler]:
    """把 OpenAI ``FunctionTool`` handler 包上 ArcReel 權限閘門。

    OpenAI Agents SDK 0.1.x 的 per-tool 攔截點是 ``on_invoke_tool``;deny 時直接
    回傳可序列化 dict,讓 SDK 當作正常 tool output 餵回模型。
    """

    def decorate(handler: OpenAIToolHandler) -> OpenAIToolHandler:
        async def wrapped(ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
            decision = gate.check(tool_name, args, _session_id_from_openai_context(ctx))
            handler_context = _handler_context_from_openai_context(ctx)
            if isinstance(decision, AskUser):
                denied = await _resolve_ask_user_decision(decision, tool_name, handler_context)
                if denied is not None:
                    return denied
                return await handler(handler_context, args)
            denied = _decision_to_denied_payload(decision, tool_name)
            if denied is None:
                return await handler(handler_context, args)
            return denied

        return wrapped

    return decorate


def as_adk_callback(gate: PermissionGate) -> Callable:
    """把 ArcReel 權限閘門包裝為 ADK before_tool_callback。"""

    async def before_tool_callback(tool: Any, args: dict[str, Any], tool_context: Any) -> dict[str, Any] | None:
        session = getattr(tool_context, "session", None)
        session_id = session.id if session else "unknown"
        decision = gate.check(tool.name, args, session_id)
        if isinstance(decision, AskUser):
            return await _resolve_ask_user_decision(decision, tool.name, _adk_handler_context(tool_context))
        return _decision_to_denied_payload(decision, tool.name)

    return before_tool_callback
