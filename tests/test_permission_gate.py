"""``server.agent_runtime.permission_gate`` 单元测试。

覆盖 spec ``assistant-tool-sandbox`` 中权限闸门要求：默认放行、Deny 不抛异常、
自定义实现可挂载、Deny 携带 reason。
"""

from __future__ import annotations

from typing import Any

import pytest

from server.agent_runtime.permission_gate import (
    Allow,
    AlwaysAllowGate,
    AskUser,
    CallableGate,
    Deny,
    PermissionGate,
    get_default_gate,
    set_default_gate,
)


def test_always_allow_gate_returns_allow() -> None:
    gate = AlwaysAllowGate()
    decision = gate.check("fs_write", {"path": "scripts/x.json"}, "session-1")
    assert isinstance(decision, Allow)


def test_always_allow_gate_asks_user_before_media_generation() -> None:
    gate = AlwaysAllowGate()

    storyboard = gate.check("generate_storyboard", {"episode": 2}, "session-1")
    assert isinstance(storyboard, AskUser)
    assert storyboard.question == "確定要開始生成第 2 集的分鏡圖嗎？"

    character_sheet = gate.check("generate_character_sheets", {"names": ["小明", "小紅"]}, "session-1")
    assert isinstance(character_sheet, AskUser)
    assert character_sheet.question == "確定要開始生成 2 個指定角色設計圖嗎？"

    video = gate.check("generate_video", {"episode": 3, "scene_ids": ["E3S01", "E3S02"]}, "session-1")
    assert isinstance(video, AskUser)
    assert video.question == "確定要開始生成第 3 集的 2 個指定分鏡影片嗎？"


def test_always_allow_gate_asks_user_before_media_generation_via_run_subagent() -> None:
    gate = AlwaysAllowGate()

    decision = gate.check("run_subagent", {"skill": "generate_video", "args": {"episode": 4}}, "session-1")

    assert isinstance(decision, AskUser)
    assert decision.question == "確定要開始生成第 4 集的影片嗎？"


def test_default_gate_is_always_allow() -> None:
    assert isinstance(get_default_gate(), AlwaysAllowGate)


def test_set_default_gate_replaces_singleton() -> None:
    class _Custom:
        def check(self, tool_name: str, args: dict[str, Any], session_id: str) -> Deny:
            return Deny("nope")

    original = get_default_gate()
    try:
        set_default_gate(_Custom())
        decision = get_default_gate().check("fs_read", {}, "s1")
        assert isinstance(decision, Deny)
        assert decision.reason == "nope"
    finally:
        set_default_gate(original)


def test_callable_gate_with_decision_object() -> None:
    gate = CallableGate(lambda tool, args, sid: Deny(f"reject {tool}"))
    decision = gate.check("fs_write", {}, "s1")
    assert isinstance(decision, Deny)
    assert decision.reason == "reject fs_write"


def test_callable_gate_maps_truthy_to_allow() -> None:
    gate = CallableGate(lambda *_args, **_kw: True)
    assert isinstance(gate.check("fs_read", {}, "s1"), Allow)


def test_callable_gate_maps_none_to_allow() -> None:
    gate = CallableGate(lambda *_args, **_kw: None)
    assert isinstance(gate.check("fs_read", {}, "s1"), Allow)


def test_callable_gate_maps_false_to_deny() -> None:
    gate = CallableGate(lambda *_args, **_kw: False)
    decision = gate.check("fs_write", {}, "s1")
    assert isinstance(decision, Deny)
    assert decision.reason == "rejected"


def test_callable_gate_maps_string_to_deny_with_reason() -> None:
    gate = CallableGate(lambda *_args, **_kw: "no write during freeze")
    decision = gate.check("fs_write", {}, "s1")
    assert isinstance(decision, Deny)
    assert decision.reason == "no write during freeze"


def test_callable_gate_passthrough_ask_user() -> None:
    gate = CallableGate(lambda *_args, **_kw: AskUser("approve fs_write?"))
    decision = gate.check("fs_write", {}, "s1")
    assert isinstance(decision, AskUser)
    assert decision.question == "approve fs_write?"


def test_callable_gate_unsupported_return_raises() -> None:
    gate = CallableGate(lambda *_args, **_kw: 42)
    with pytest.raises(TypeError):
        gate.check("fs_write", {}, "s1")


def test_protocol_compliance() -> None:
    """Both built-in implementations must satisfy the PermissionGate protocol."""
    instances: list[PermissionGate] = [AlwaysAllowGate(), CallableGate(lambda *a, **k: True)]
    for gate in instances:
        decision = gate.check("any_tool", {"k": "v"}, "session-x")
        assert isinstance(decision, (Allow, Deny, AskUser))


@pytest.mark.asyncio
async def test_openai_wrapper_allows_and_calls_handler() -> None:
    from server.agent_runtime.permission_gate import as_openai_wrapper

    calls: list[tuple[Any, dict[str, Any]]] = []

    class _Ctx:
        session_id = "openai-full:test"

    async def handler(ctx: _Ctx, args: dict[str, Any]) -> dict[str, Any]:
        calls.append((ctx, args))
        return {"ok": True, "args": args}

    ctx = _Ctx()
    wrapped = as_openai_wrapper(AlwaysAllowGate(), "fs_read")(handler)

    result = await wrapped(ctx, {"path": "source/a.txt"})

    assert result == {"ok": True, "args": {"path": "source/a.txt"}}
    assert calls == [(ctx, {"path": "source/a.txt"})]


@pytest.mark.asyncio
async def test_openai_wrapper_denies_without_calling_handler() -> None:
    from server.agent_runtime.permission_gate import as_openai_wrapper

    called = False

    async def handler(_ctx: Any, _args: dict[str, Any]) -> dict[str, Any]:
        nonlocal called
        called = True
        return {"ok": True}

    wrapped = as_openai_wrapper(CallableGate(lambda *_args: Deny("user rejected")), "fs_write")(handler)

    result = await wrapped(type("Ctx", (), {"session_id": "openai-full:test"})(), {"path": "scripts/x.json"})

    assert result == {
        "permission_denied": True,
        "reason": "user rejected",
        "tool": "fs_write",
    }
    assert called is False


@pytest.mark.asyncio
async def test_openai_and_adk_deny_payloads_share_canonical_shape() -> None:
    from server.agent_runtime.permission_gate import as_adk_callback, as_openai_wrapper

    gate = CallableGate(lambda *_args: Deny("user rejected"))

    async def handler(_ctx: Any, _args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True}

    class _OpenAICtx:
        session_id = "openai-full:test"

    class _AdkTool:
        name = "fs_write"

    class _AdkContext:
        class session:
            id = "gemini-full:test"

    openai_payload = await as_openai_wrapper(gate, "fs_write")(handler)(_OpenAICtx(), {"path": "scripts/x.json"})
    adk_payload = await as_adk_callback(gate)(_AdkTool(), {"path": "scripts/x.json"}, _AdkContext())

    assert (
        openai_payload
        == adk_payload
        == {
            "permission_denied": True,
            "reason": "user rejected",
            "tool": "fs_write",
        }
    )
