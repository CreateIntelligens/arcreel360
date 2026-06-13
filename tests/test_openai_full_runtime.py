"""OpenAI full-tier assistant runtime provider tests."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from agents import Agent
from agents.items import MessageOutputItem, ToolCallItem, ToolCallOutputItem
from agents.stream_events import RawResponsesStreamEvent, RunItemStreamEvent
from google.adk.events.event import Event
from google.genai.types import Content, FunctionCall, FunctionResponse, Part
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseTextDeltaEvent,
)

from server.agent_runtime.adk_gemini_full_runtime_provider import AdkGeminiFullRuntimeProvider
from server.agent_runtime.openai_full_runtime_provider import DEFAULT_OPENAI_FULL_MODEL, OpenAIFullRuntimeProvider
from server.agent_runtime.openai_tool_adapters import OPENAI_TOOL_DECLARATIONS
from server.agent_runtime.permission_gate import AlwaysAllowGate
from server.agent_runtime.session_identity import OPENAI_FULL_PROVIDER_ID
from server.agent_runtime.text_backend_runtime_provider import LiteManagedSession


@dataclass
class _Meta:
    project_name: str
    status: str = "idle"


class _FakeMetaStore:
    def __init__(self) -> None:
        self.sessions: dict[str, _Meta] = {}

    async def create(self, project_name: str, sdk_session_id: str) -> _Meta:
        meta = _Meta(project_name=project_name)
        self.sessions[sdk_session_id] = meta
        return meta

    async def get(self, session_id: str) -> _Meta | None:
        return self.sessions.get(session_id)

    async def update_status(self, session_id: str, status: str) -> bool:
        self.sessions.setdefault(session_id, _Meta(project_name="demo")).status = status
        return True


class _ResolverSession:
    def __init__(self, provider_id: str, model_id: str | None) -> None:
        self._provider_id = provider_id
        self._model_id = model_id

    async def __aenter__(self) -> _ResolverSession:
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    async def default_text_backend(self) -> tuple[str, str | None]:
        return self._provider_id, self._model_id


class _Resolver:
    def __init__(self, provider_id: str, model_id: str | None) -> None:
        self._provider_id = provider_id
        self._model_id = model_id

    def session(self) -> _ResolverSession:
        return _ResolverSession(self._provider_id, self._model_id)


async def _noop_persist(_session_id: str, _message: dict[str, Any]) -> None:
    return None


async def _empty_history(_session_id: str) -> list[dict[str, Any]]:
    return []


async def _wait_for(predicate: Callable[[], bool]) -> None:
    while not predicate():
        await asyncio.sleep(0.01)


@pytest.fixture
def provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> OpenAIFullRuntimeProvider:
    project_root = tmp_path
    project_dir = project_root / "projects" / "demo"
    project_dir.mkdir(parents=True)
    (project_dir / "project.json").write_text(
        json.dumps({"title": "demo", "characters": {}, "clues": {}, "episodes": []}),
        encoding="utf-8",
    )

    runtime = OpenAIFullRuntimeProvider(
        project_root=project_root,
        data_dir=project_root / "data",
        meta_store=_FakeMetaStore(),  # type: ignore[arg-type]
        permission_gate=AlwaysAllowGate(),
    )
    monkeypatch.setattr(runtime, "_persist_message", _noop_persist)
    monkeypatch.setattr(runtime, "_load_history", _empty_history)
    return runtime


def _text_delta_event(text: str) -> RawResponsesStreamEvent:
    return RawResponsesStreamEvent(
        data=ResponseTextDeltaEvent(
            content_index=0,
            delta=text,
            item_id="msg_1",
            logprobs=[],
            output_index=0,
            sequence_number=0,
            type="response.output_text.delta",
        )
    )


def _message_output_event(agent: Agent[Any], text: str) -> RunItemStreamEvent:
    item = MessageOutputItem(
        agent=agent,
        raw_item=ResponseOutputMessage(
            id="msg_1",
            content=[ResponseOutputText(annotations=[], text=text, type="output_text")],
            role="assistant",
            status="completed",
            type="message",
        ),
    )
    return RunItemStreamEvent(name="message_output_created", item=item)


def _tool_call_event(agent: Agent[Any], name: str, args: dict[str, Any], call_id: str) -> RunItemStreamEvent:
    item = ToolCallItem(
        agent=agent,
        raw_item=ResponseFunctionToolCall(
            id="fc_1",
            call_id=call_id,
            name=name,
            arguments=json.dumps(args),
            status="completed",
            type="function_call",
        ),
    )
    return RunItemStreamEvent(name="tool_called", item=item)


def _tool_output_event(agent: Agent[Any], output: Any, call_id: str) -> RunItemStreamEvent:
    item = ToolCallOutputItem(
        agent=agent,
        raw_item={"type": "function_call_output", "call_id": call_id, "output": json.dumps(output)},
        output=output,
    )
    return RunItemStreamEvent(name="tool_output", item=item)


def _adk_tool_call_event(name: str, args: dict[str, Any], call_id: str) -> Event:
    return Event(
        author="model",
        content=Content(parts=[Part(function_call=FunctionCall(name=name, args=args, id=call_id))]),
    )


def _adk_tool_result_event(name: str, response: Any, call_id: str) -> Event:
    return Event(
        author="user",
        content=Content(parts=[Part(function_response=FunctionResponse(name=name, response=response, id=call_id))]),
    )


def test_provider_capabilities_and_agent_tools(provider: OpenAIFullRuntimeProvider) -> None:
    assert provider.provider_id == OPENAI_FULL_PROVIDER_ID
    assert provider.capabilities.provider == OPENAI_FULL_PROVIDER_ID
    assert provider.capabilities.tier == "full"
    assert provider.capabilities.supports_streaming is True
    assert provider.capabilities.supports_images is True
    assert provider.capabilities.supports_tool_calls is True
    assert provider.capabilities.supports_interrupt is True
    assert provider.capabilities.supports_resume is True
    assert provider.capabilities.supports_subagents is True
    assert provider.capabilities.supports_permission_hooks is True

    # tools 在 __init__ 預先建好並 cache 在 self._tools(避免每次 _build_agent 重建);
    # _build_agent 會把 model + project_name 注入並重用 self._tools。
    assert {tool.name for tool in provider._tools} == {declaration.name for declaration in OPENAI_TOOL_DECLARATIONS}
    agent = provider._build_agent(DEFAULT_OPENAI_FULL_MODEL)
    assert agent.model == DEFAULT_OPENAI_FULL_MODEL
    assert agent.tools is provider._tools


def test_openai_full_instructions_require_traditional_chinese(provider: OpenAIFullRuntimeProvider) -> None:
    instructions = provider._build_openai_instructions("demo")

    assert "繁體中文" in instructions


@pytest.mark.asyncio
async def test_resolve_model_name_uses_openai_config_model(provider: OpenAIFullRuntimeProvider) -> None:
    provider._resolver = _Resolver("openai", "gpt-4.1")  # type: ignore[assignment]

    assert await provider._resolve_model_name() == "gpt-4.1"


@pytest.mark.asyncio
async def test_send_new_session_uses_openai_full_prefix_and_writes_user_echo(
    provider: OpenAIFullRuntimeProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_generation(
        managed: LiteManagedSession,
        _prompt: str,
        *,
        echo_text: str | None,
        echo_content: list[dict[str, Any]] | None,
    ) -> None:
        managed.status = "completed"
        await provider._meta_store.update_status(managed.session_id, "completed")
        managed.add_message(provider._build_runtime_status_message(managed.session_id, managed.status))

    monkeypatch.setattr(provider, "_run_generation", fake_run_generation)

    session_id = await provider.send_new_session("demo", "hello", echo_text="hello")
    await provider._sessions[session_id].generation_task

    assert re.match(r"^openai-full:[0-9a-f]{32}$", session_id)
    messages = provider.get_buffered_messages(session_id)
    assert messages[0]["type"] == "user"
    assert messages[0]["content"] == [{"type": "text", "text": "hello"}]
    assert messages[0]["local_echo"] is True


def test_agent_messages_convert_to_openai_input(provider: OpenAIFullRuntimeProvider) -> None:
    input_items = provider._messages_to_openai_input(
        [
            {"type": "user", "content": [{"type": "text", "text": "first"}]},
            {"type": "assistant", "content": [{"type": "text", "text": "reply"}]},
            {"type": "tool_use", "tool_use_id": "call_1", "name": "fs_read", "input": {"path": "project.json"}},
            {"type": "tool_result", "tool_use_id": "call_1", "content": {"content": "{}"}, "is_error": False},
            {"type": "stream_event", "delta": {"type": "text_delta", "text": "ignored"}},
            {"type": "result", "subtype": "success"},
        ]
    )

    assert input_items[0] == {"role": "user", "content": "first"}
    assert input_items[1] == {"role": "assistant", "content": "reply"}
    assert input_items[2]["type"] == "function_call"
    assert input_items[2]["call_id"] == "call_1"
    assert input_items[2]["name"] == "fs_read"
    assert json.loads(input_items[2]["arguments"]) == {"path": "project.json"}
    assert input_items[3]["type"] == "function_call_output"
    assert input_items[3]["call_id"] == "call_1"
    assert json.loads(input_items[3]["output"]) == {"content": "{}"}


@pytest.mark.asyncio
async def test_runner_run_streamed_receives_history_and_no_sdk_session(
    provider: OpenAIFullRuntimeProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = "openai-full:" + "a" * 32
    provider._sessions[session_id] = LiteManagedSession(
        session_id=session_id,
        project_name="demo",
        persist_callback=_noop_persist,
    )
    provider._meta_store.sessions[session_id] = _Meta(project_name="demo")  # type: ignore[attr-defined]
    monkeypatch.setattr(provider, "_resolver", _Resolver("openai", "gpt-test"))

    async def fake_load_history(_session_id: str) -> list[dict[str, Any]]:
        return [
            {"type": "user", "content": [{"type": "text", "text": "previous"}]},
            {"type": "assistant", "content": [{"type": "text", "text": "old answer"}]},
        ]

    monkeypatch.setattr(provider, "_load_history", fake_load_history)

    captured: dict[str, Any] = {}

    class _Run:
        async def stream_events(self) -> AsyncIterator[Any]:
            yield _text_delta_event("ok")

    def fake_run_streamed(*args: Any, **kwargs: Any) -> _Run:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _Run()

    monkeypatch.setattr("server.agent_runtime.openai_full_runtime_provider.Runner.run_streamed", fake_run_streamed)

    await provider.send_message(session_id, "next", echo_text="next")
    await provider._sessions[session_id].generation_task

    kwargs = captured["kwargs"]
    assert "session" not in kwargs
    assert kwargs["max_turns"] == 20
    assert kwargs["context"].session_id == session_id
    assert kwargs["input"][0] == {"role": "user", "content": "previous"}
    assert kwargs["input"][1] == {"role": "assistant", "content": "old answer"}
    assert kwargs["input"][-1] == {"role": "user", "content": "next"}


def test_project_to_sse_maps_openai_stream_events(provider: OpenAIFullRuntimeProvider) -> None:
    session_id = "openai-full:" + "b" * 32
    managed = LiteManagedSession(session_id=session_id, project_name="demo", persist_callback=None)
    agent = Agent(name="test-agent", instructions="test")

    provider._project_to_sse(managed, _text_delta_event("讀"), "gpt-test")
    provider._project_to_sse(
        managed, _tool_call_event(agent, "fs_read", {"path": "project.json"}, "call_1"), "gpt-test"
    )
    provider._project_to_sse(managed, _tool_output_event(agent, {"content": "{}"}, "call_1"), "gpt-test")
    provider._project_to_sse(managed, _message_output_event(agent, "讀完"), "gpt-test")

    messages = managed.message_buffer
    assert messages[0]["type"] == "stream_event"
    assert messages[0]["delta"] == {"type": "text_delta", "text": "讀"}
    assert messages[1]["type"] == "tool_use"
    assert messages[1]["tool_use_id"] == "call_1"
    assert messages[1]["name"] == "fs_read"
    assert messages[1]["input"] == {"path": "project.json"}
    assert messages[2]["type"] == "tool_result"
    assert messages[2]["tool_use_id"] == "call_1"
    assert messages[2]["content"] == {"content": "{}"}
    assert messages[2]["is_error"] is False
    assert messages[3]["type"] == "assistant"
    assert messages[3]["content"] == [{"type": "text", "text": "讀完"}]


@pytest.mark.asyncio
async def test_request_approval_publishes_pending_question_and_waits_for_answer(
    provider: OpenAIFullRuntimeProvider,
) -> None:
    session_id = "openai-full:" + "9" * 32
    managed = LiteManagedSession(session_id=session_id, project_name="demo", status="running", persist_callback=None)
    provider._sessions[session_id] = managed

    payload = {
        "type": "ask_user_question",
        "question_id": "approval_1",
        "questions": [
            {
                "header": "確認",
                "question": "確定要開始生成第 1 集的影片嗎？",
                "options": [
                    {"label": "確認生成", "description": "開始執行這個生成任務"},
                    {"label": "取消", "description": "不要執行這個生成任務"},
                ],
                "multiSelect": False,
                "allowOther": False,
            }
        ],
    }

    approval_task = asyncio.create_task(provider._request_approval(managed, payload))
    await asyncio.wait_for(_wait_for(lambda: bool(managed.get_pending_question_payloads())), timeout=1)

    assert await provider.get_pending_questions_snapshot(session_id) == [payload]
    assert managed.message_buffer[-1] == payload

    await provider.answer_user_question(
        session_id,
        "approval_1",
        {"確定要開始生成第 1 集的影片嗎？": "確認生成"},
    )

    assert await asyncio.wait_for(approval_task, timeout=1) == {
        "確定要開始生成第 1 集的影片嗎？": "確認生成",
    }
    assert await provider.get_pending_questions_snapshot(session_id) == []


@pytest.mark.asyncio
async def test_runner_stream_persists_multiple_tool_calls_and_permission_deny(
    provider: OpenAIFullRuntimeProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = "openai-full:" + "e" * 32
    provider._sessions[session_id] = LiteManagedSession(
        session_id=session_id,
        project_name="demo",
        persist_callback=_noop_persist,
    )
    provider._meta_store.sessions[session_id] = _Meta(project_name="demo")  # type: ignore[attr-defined]
    monkeypatch.setattr(provider, "_resolver", _Resolver("openai", "gpt-test"))
    agent = Agent(name="test-agent", instructions="test")
    deny_payload = {
        "permission_denied": True,
        "reason": "user rejected",
        "tool": "fs_write",
    }

    class _Run:
        async def stream_events(self) -> AsyncIterator[Any]:
            yield _tool_call_event(agent, "fs_read", {"path": "project.json"}, "call_read")
            yield _tool_output_event(agent, {"content": "{}"}, "call_read")
            yield _tool_call_event(agent, "fs_write", {"path": "scripts/x.json", "content": "{}"}, "call_write")
            yield _tool_output_event(agent, deny_payload, "call_write")
            yield _message_output_event(agent, "已改用不寫檔方案。")

    monkeypatch.setattr(
        "server.agent_runtime.openai_full_runtime_provider.Runner.run_streamed",
        lambda *_args, **_kwargs: _Run(),
    )

    await provider.send_message(session_id, "run tools", echo_text="run tools")
    await provider._sessions[session_id].generation_task

    messages = provider.get_buffered_messages(session_id)
    tool_uses = [message for message in messages if message.get("type") == "tool_use"]
    tool_results = [message for message in messages if message.get("type") == "tool_result"]
    assert [message["name"] for message in tool_uses] == ["fs_read", "fs_write"]
    assert [message["tool_use_id"] for message in tool_results] == ["call_read", "call_write"]
    assert tool_results[1]["content"] == deny_payload
    assert tool_results[1]["is_error"] is False
    assert provider._sessions[session_id].status == "completed"


def test_permission_deny_sse_payload_matches_adk_gemini_canonical_shape(
    provider: OpenAIFullRuntimeProvider,
    tmp_path: Path,
) -> None:
    deny_payload = {
        "permission_denied": True,
        "reason": "user rejected",
        "tool": "fs_write",
    }
    openai_managed = LiteManagedSession(
        session_id="openai-full:" + "f" * 32,
        project_name="demo",
        persist_callback=None,
    )
    adk_provider = AdkGeminiFullRuntimeProvider(
        project_root=tmp_path,
        data_dir=tmp_path / "data",
        meta_store=_FakeMetaStore(),  # type: ignore[arg-type]
        permission_gate=AlwaysAllowGate(),
    )
    adk_managed = LiteManagedSession(
        session_id="gemini-full:" + "f" * 32,
        project_name="demo",
        persist_callback=None,
    )
    agent = Agent(name="test-agent", instructions="test")

    provider._project_to_sse(
        openai_managed,
        _tool_call_event(agent, "fs_write", {"path": "scripts/x.json", "content": "{}"}, "call_deny"),
        "gpt-test",
    )
    provider._project_to_sse(openai_managed, _tool_output_event(agent, deny_payload, "call_deny"), "gpt-test")
    adk_provider._project_to_sse(
        adk_managed,
        _adk_tool_call_event("fs_write", {"path": "scripts/x.json", "content": "{}"}, "call_deny"),
        "gemini-test",
    )
    adk_provider._project_to_sse(
        adk_managed,
        _adk_tool_result_event("fs_write", deny_payload, "call_deny"),
        "gemini-test",
    )

    openai_events = [
        message for message in openai_managed.message_buffer if message.get("type") in {"tool_use", "tool_result"}
    ]
    adk_events = [
        message for message in adk_managed.message_buffer if message.get("type") in {"tool_use", "tool_result"}
    ]

    assert [message["type"] for message in openai_events] == [message["type"] for message in adk_events]
    assert openai_events[0]["name"] == adk_events[0]["name"] == "fs_write"
    assert openai_events[1]["content"] == adk_events[1]["content"] == deny_payload
    assert openai_events[1]["is_error"] is adk_events[1]["is_error"] is False


@pytest.mark.asyncio
async def test_heartbeat_timeout_marks_session_error(
    provider: OpenAIFullRuntimeProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = "openai-full:" + "c" * 32
    provider._sessions[session_id] = LiteManagedSession(
        session_id=session_id,
        project_name="demo",
        persist_callback=_noop_persist,
    )
    provider._meta_store.sessions[session_id] = _Meta(project_name="demo")  # type: ignore[attr-defined]
    monkeypatch.setattr(provider, "_resolver", _Resolver("openai", "gpt-test"))
    monkeypatch.setenv("ASSISTANT_STREAM_HEARTBEAT_SECONDS", "0.01")

    class _SlowRun:
        async def stream_events(self) -> AsyncIterator[Any]:
            await asyncio.sleep(1)
            yield _text_delta_event("late")

    monkeypatch.setattr(
        "server.agent_runtime.openai_full_runtime_provider.Runner.run_streamed",
        lambda *_args, **_kwargs: _SlowRun(),
    )

    await provider.send_message(session_id, "next", echo_text="next")
    await provider._sessions[session_id].generation_task

    assert provider._sessions[session_id].status == "error"
    result = next(message for message in provider.get_buffered_messages(session_id) if message.get("type") == "result")
    assert result["subtype"] == "timeout"
    assert result["is_error"] is True


@pytest.mark.asyncio
async def test_interrupt_session_stops_waiting_stream_without_waiting_for_heartbeat(
    provider: OpenAIFullRuntimeProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = "openai-full:" + "d" * 32
    provider._sessions[session_id] = LiteManagedSession(
        session_id=session_id,
        project_name="demo",
        persist_callback=_noop_persist,
    )
    provider._meta_store.sessions[session_id] = _Meta(project_name="demo")  # type: ignore[attr-defined]
    monkeypatch.setattr(provider, "_resolver", _Resolver("openai", "gpt-test"))
    monkeypatch.setenv("ASSISTANT_STREAM_HEARTBEAT_SECONDS", "30")
    stream_waiting = asyncio.Event()

    class _BlockedRun:
        async def stream_events(self) -> AsyncIterator[Any]:
            stream_waiting.set()
            await asyncio.Event().wait()
            yield _text_delta_event("late")

    monkeypatch.setattr(
        "server.agent_runtime.openai_full_runtime_provider.Runner.run_streamed",
        lambda *_args, **_kwargs: _BlockedRun(),
    )

    await provider.send_message(session_id, "next", echo_text="next")
    await asyncio.wait_for(stream_waiting.wait(), timeout=1)

    assert await provider.interrupt_session(session_id) == "interrupted"
    await asyncio.wait_for(provider._sessions[session_id].generation_task, timeout=1)

    assert provider._sessions[session_id].status == "interrupted"
    result = next(message for message in provider.get_buffered_messages(session_id) if message.get("type") == "result")
    assert result["subtype"] == "error_interrupt"
    assert result["is_error"] is True
