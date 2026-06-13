"""``AdkGeminiFullRuntimeProvider`` 单元测试."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from google.adk.events.event import Event
from google.genai.types import Content, FunctionCall, FunctionResponse, Part

from lib.project_manager import ProjectManager
from server.agent_runtime.adk_gemini_full_runtime_provider import AdkGeminiFullRuntimeProvider
from server.agent_runtime.permission_gate import AlwaysAllowGate
from server.agent_runtime.session_store import SessionMetaStore

# ---------------------------------------------------------------------------
# ADK Event Helpers
# ---------------------------------------------------------------------------


def _make_text_event(text: str, author: str = "model") -> Event:
    return Event(author=author, content=Content(parts=[Part(text=text)]))


def _make_tool_call_event(name: str, args: dict[str, Any], call_id: str = None) -> Event:
    return Event(
        author="model",
        content=Content(parts=[Part(function_call=FunctionCall(name=name, args=args, id=call_id or uuid4().hex))]),
    )


def _make_tool_result_event(name: str, response: Any, call_id: str) -> Event:
    return Event(
        author="user",
        content=Content(parts=[Part(function_response=FunctionResponse(name=name, response=response, id=call_id))]),
    )


# ---------------------------------------------------------------------------
# Provider Setup
# ---------------------------------------------------------------------------


@pytest.fixture
def provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AdkGeminiFullRuntimeProvider:
    project_root = tmp_path
    (project_root / "projects" / "demo").mkdir(parents=True)
    pm = ProjectManager(projects_root=str(project_root / "projects"))
    pm.save_project(
        "demo",
        {"title": "demo", "characters": {}, "clues": {}, "episodes": []},
    )

    meta_store = SessionMetaStore()
    p = AdkGeminiFullRuntimeProvider(
        project_root=project_root,
        data_dir=project_root / "data",
        meta_store=meta_store,
        permission_gate=AlwaysAllowGate(),
    )

    # Mock _get_genai_client
    async def fake_get_client():
        return MagicMock(), "gemini-fake"

    monkeypatch.setattr(p, "_get_genai_client", fake_get_client)

    # Mock session service methods to avoid DB
    async def _noop_create(*a, **k):
        from google.adk.session_service import Session

        return Session(id=k.get("session_id") or "test-session", app_name="arcreel", user_id="demo", state={})

    # Mock meta_store
    class _FakeMetaStore:
        async def create(self, *a, **k):
            pass

        async def update_status(self, *a, **k):
            pass

        async def get(self, *a, **k):
            return None

    monkeypatch.setattr(p, "_meta_store", _FakeMetaStore())

    return p


def _patch_runner(provider: AdkGeminiFullRuntimeProvider, monkeypatch: pytest.MonkeyPatch, events: list[Event]):
    mock_runner = MagicMock()

    async def fake_run_async(*a, **k) -> AsyncGenerator[Event, None]:
        for e in events:
            yield e

    mock_runner.run_async = fake_run_async

    # Patch the Runner class in the provider module
    monkeypatch.setattr("server.agent_runtime.adk_gemini_full_runtime_provider.Runner", lambda **k: mock_runner)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_system_prompt_requires_traditional_chinese(provider: AdkGeminiFullRuntimeProvider) -> None:
    prompt = provider._build_system_prompt("demo")

    assert "繁體中文" in prompt


@pytest.mark.asyncio
async def test_single_turn_text_only(provider: AdkGeminiFullRuntimeProvider, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_runner(provider, monkeypatch, [_make_text_event("你好")])

    sid = await provider.send_new_session("demo", "嗨", echo_text="嗨")
    managed = provider._sessions[sid]
    await managed.generation_task

    buf = managed.message_buffer
    types = [m.get("type") for m in buf]
    assert "user" in types
    assert "assistant" in types

    assistant_msg = next(m for m in buf if m["type"] == "assistant")
    assert assistant_msg["content"][0]["text"] == "你好"
    assert managed.status == "completed"


@pytest.mark.asyncio
async def test_tool_use_and_result(provider: AdkGeminiFullRuntimeProvider, monkeypatch: pytest.MonkeyPatch) -> None:
    call_id = "call_123"
    events = [
        _make_tool_call_event("fs_read", {"path": "scripts/ep1.json"}, call_id=call_id),
        _make_tool_result_event("fs_read", {"content": "hello"}, call_id=call_id),
        _make_text_event("已讀完"),
    ]
    _patch_runner(provider, monkeypatch, events)

    # Setup file
    target = provider._project_root / "projects" / "demo" / "scripts"
    target.mkdir(parents=True, exist_ok=True)
    (target / "ep1.json").write_text("hello")

    sid = await provider.send_new_session("demo", "讀檔案", echo_text="讀檔案")
    managed = provider._sessions[sid]
    await managed.generation_task

    buf = managed.message_buffer
    tool_uses = [m for m in buf if m.get("type") == "tool_use"]
    tool_results = [m for m in buf if m.get("type") == "tool_result"]
    assert len(tool_uses) == 1
    assert len(tool_results) == 1
    assert tool_results[0]["content"]["content"] == "hello"
    assert managed.status == "completed"


@pytest.mark.asyncio
async def test_streaming_text_deltas(provider: AdkGeminiFullRuntimeProvider, monkeypatch: pytest.MonkeyPatch) -> None:
    events = [
        _make_text_event("你"),
        _make_text_event("好"),
        _make_text_event("！"),
    ]
    _patch_runner(provider, monkeypatch, events)

    sid = await provider.send_new_session("demo", "嗨", echo_text="嗨")
    managed = provider._sessions[sid]
    await managed.generation_task

    buf = managed.message_buffer
    deltas = [m for m in buf if m.get("type") == "stream_event"]
    assert len(deltas) == 3
    assert [d["delta"]["text"] for d in deltas] == ["你", "好", "！"]

    assistant_msg = next(m for m in buf if m["type"] == "assistant")
    assert assistant_msg["content"][0]["text"] == "你好！"
