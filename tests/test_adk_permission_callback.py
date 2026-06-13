from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from server.agent_runtime.permission_gate import AlwaysAllowGate, AskUser, Deny, PermissionGate, as_adk_callback


@pytest.fixture
def mock_tool():
    tool = Mock()
    tool.name = "test_tool"
    return tool


@pytest.fixture
def mock_context():
    ctx = Mock()
    ctx.session.id = "test_session_id"
    return ctx


@pytest.mark.asyncio
async def test_always_allow_gate(mock_tool, mock_context):
    gate = AlwaysAllowGate()
    callback = as_adk_callback(gate)

    result = await callback(mock_tool, {"arg": 1}, mock_context)
    assert result is None


@pytest.mark.asyncio
async def test_deny_gate(mock_tool, mock_context):
    gate = Mock(spec=PermissionGate)
    gate.check.return_value = Deny("test reason")

    callback = as_adk_callback(gate)
    result = await callback(mock_tool, {"arg": 1}, mock_context)

    assert result == {"permission_denied": True, "reason": "test reason", "tool": "test_tool"}


@pytest.mark.asyncio
async def test_ask_user_gate(mock_tool, mock_context):
    gate = Mock(spec=PermissionGate)
    gate.check.return_value = AskUser("are you sure?")

    callback = as_adk_callback(gate)
    result = await callback(mock_tool, {"arg": 1}, mock_context)

    assert result == {
        "permission_denied": True,
        "reason": "approval_required",
        "question": "are you sure?",
        "tool": "test_tool",
    }


@pytest.mark.asyncio
async def test_media_generation_waits_for_button_approval_in_adk_callback(mock_context):
    tool = Mock()
    tool.name = "generate_video"
    approvals = []

    async def approval_requester(payload):
        approvals.append(payload)
        question = payload["questions"][0]["question"]
        return {question: "確認生成"}

    mock_context.state = {"skill_ctx": SimpleNamespace(approval_requester=approval_requester)}
    callback = as_adk_callback(AlwaysAllowGate())

    result = await callback(tool, {"episode": 3}, mock_context)

    assert result is None
    assert approvals[0]["questions"][0]["question"] == "確定要開始生成第 3 集的影片嗎？"


@pytest.mark.asyncio
async def test_media_generation_cancel_button_blocks_adk_callback(mock_context):
    tool = Mock()
    tool.name = "generate_storyboard"

    async def approval_requester(payload):
        question = payload["questions"][0]["question"]
        return {question: "取消"}

    mock_context.state = {"skill_ctx": SimpleNamespace(approval_requester=approval_requester)}
    callback = as_adk_callback(AlwaysAllowGate())

    result = await callback(tool, {"episode": 1}, mock_context)

    assert result == {
        "permission_denied": True,
        "reason": "user_cancelled",
        "question": "確定要開始生成第 1 集的分鏡圖嗎？",
        "tool": "generate_storyboard",
    }
