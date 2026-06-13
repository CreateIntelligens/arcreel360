"""OpenAI Agents SDK-backed full-tier assistant runtime provider."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from agents import Agent, RunConfig, Runner
from agents.exceptions import MaxTurnsExceeded
from agents.items import ItemHelpers, MessageOutputItem, ToolCallItem, ToolCallOutputItem
from agents.stream_events import RawResponsesStreamEvent, RunItemStreamEvent

from lib.project_manager import ProjectManager
from server.agent_runtime.message_utils import extract_plain_user_content
from server.agent_runtime.openai_tool_adapters import OPENAI_TOOL_DECLARATIONS, OPENAI_TOOL_HANDLERS, build_skill_tools
from server.agent_runtime.permission_gate import PermissionGate, get_default_gate
from server.agent_runtime.runtime_provider import AssistantPrompt, AssistantProviderCapabilities
from server.agent_runtime.session_identity import OPENAI_FULL_PROVIDER_ID
from server.agent_runtime.session_store import SessionMetaStore
from server.agent_runtime.skill_function_declarations import SkillCallContext
from server.agent_runtime.text_backend_runtime_provider import BaseTextBackendRuntimeProvider, LiteManagedSession
from server.agent_runtime.tool_sandbox import ToolSandbox

logger = logging.getLogger(__name__)

DEFAULT_OPENAI_FULL_MODEL = "gpt-4o"

_OPENAI_FULL_INSTRUCTIONS = """## 工具使用

你可以使用 ArcReel 的專案工具讀寫目前專案內的檔案，並呼叫漫畫工作流技能產生劇本、角色、線索、分鏡、影片與剪輯草稿。

- 優先使用結構化工具完成專案工作，不要假裝已寫入檔案。
- 讀寫檔案時只能使用相對於目前專案根目錄的路徑。
- 權限被拒絕時，根據 tool_result 的原因調整方案，不要重試同一個被拒絕的操作。
- 工具結果是專案狀態的真相來源；回覆使用者時簡潔說明已完成的動作與下一步。"""


class _OpenAIStreamInterrupted(Exception):
    """Internal sentinel used to finish an interrupted stream cleanly."""


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class OpenAIFullRuntimeProvider(BaseTextBackendRuntimeProvider):
    """Full-tier runtime provider implemented with the OpenAI Agents SDK."""

    def __init__(
        self,
        *,
        project_root: Path,
        data_dir: Path,
        meta_store: SessionMetaStore,
        permission_gate: PermissionGate | None = None,
        max_tool_turns: int = 20,
    ) -> None:
        super().__init__(
            provider_id=OPENAI_FULL_PROVIDER_ID,
            capabilities=AssistantProviderCapabilities(
                provider=OPENAI_FULL_PROVIDER_ID,
                tier="full",
                supports_streaming=True,
                supports_images=True,
                supports_tool_calls=True,
                supports_interrupt=True,
                supports_resume=True,
                supports_subagents=True,
                supports_permission_hooks=True,
            ),
            project_root=project_root,
            data_dir=data_dir,
            meta_store=meta_store,
        )
        self._permission_gate = permission_gate or get_default_gate()
        self._max_tool_turns = max_tool_turns
        self._project_manager = ProjectManager(projects_root=str(project_root / "projects"))
        self._interrupt_requests: set[str] = set()
        self._interrupt_events: dict[str, asyncio.Event] = {}
        # 工具集合不依賴 model / project,建一次重用即可(每次 _build_agent
        # 都重跑 schema 轉換 + deepcopy 11 個 tool 是浪費)。
        self._tools = build_skill_tools(OPENAI_TOOL_DECLARATIONS, OPENAI_TOOL_HANDLERS, self._permission_gate)

    async def _create_backend(self, project_name: str) -> Any:
        return None

    def _build_agent(self, model_name: str, project_name: str | None = None) -> Agent[SkillCallContext]:
        return Agent(
            name="arcreel_openai_full",
            instructions=self._build_openai_instructions(project_name),
            model=model_name,
            tools=self._tools,
        )

    def _build_openai_instructions(self, project_name: str | None) -> str:
        base = self._build_system_prompt(project_name or "")
        return f"{base}\n\n{_OPENAI_FULL_INSTRUCTIONS}"

    async def _resolve_model_name(self) -> str:
        try:
            async with self._resolver.session() as resolver:
                provider_id, model_id = await resolver.default_text_backend()
        except Exception:
            logger.warning("openai-full: failed to resolve text backend, using default", exc_info=True)
            return DEFAULT_OPENAI_FULL_MODEL

        if provider_id == "openai" and model_id:
            return model_id
        return DEFAULT_OPENAI_FULL_MODEL

    async def _run_generation(
        self,
        managed: LiteManagedSession,
        prompt: AssistantPrompt,
        *,
        echo_text: str | None,
        echo_content: list[dict[str, Any]] | None,
    ) -> None:
        model_name = await self._resolve_model_name()
        agent = self._build_agent(model_name, managed.project_name)
        skill_ctx = self._build_skill_context(managed)
        self._interrupt_events.setdefault(managed.session_id, asyncio.Event()).clear()

        try:
            input_items = await self._build_openai_input(managed)
            run = Runner.run_streamed(
                agent,
                input=input_items,
                context=skill_ctx,
                max_turns=self._max_tool_turns,
                run_config=RunConfig(tracing_disabled=True),
            )
            assistant_text = await self._consume_stream(managed, run.stream_events(), model_name)
            if assistant_text.strip() and not self._has_assistant_message(managed):
                managed.add_message(self._assistant_message(assistant_text.strip(), model_name))
            await self._emit_success(managed, model_name)
        except _OpenAIStreamInterrupted:
            await self._emit_interrupted(managed)
        except asyncio.CancelledError:
            await self._emit_interrupted(managed)
            raise
        except TimeoutError as exc:
            logger.warning("openai-full: stream heartbeat timeout session=%s", managed.session_id)
            await self._emit_error(managed, "timeout", str(exc), model_name=model_name)
        except MaxTurnsExceeded as exc:
            logger.warning("openai-full: max turns exceeded session=%s", managed.session_id)
            await self._emit_error(managed, "max_turns", str(exc), model_name=model_name)
        except Exception as exc:
            logger.exception("openai-full: generation failed session=%s", managed.session_id)
            await self._emit_error(managed, "generation_failed", str(exc), model_name=model_name)
        finally:
            self._interrupt_requests.discard(managed.session_id)
            self._interrupt_events.pop(managed.session_id, None)
            managed.generation_task = None

    def _build_skill_context(self, managed: LiteManagedSession) -> SkillCallContext:
        project_root = self._project_root / "projects"
        return SkillCallContext(
            project_name=managed.project_name,
            sandbox=ToolSandbox(project_root=project_root, project_name=managed.project_name),
            project_manager=self._project_manager,
            session_id=managed.session_id,
            approval_requester=lambda payload: self._request_approval(managed, payload),
        )

    async def _build_openai_input(self, managed: LiteManagedSession) -> list[dict[str, Any]]:
        history = await self._load_history(managed.session_id)
        messages = self._merge_history_with_live_buffer(history, managed.message_buffer)
        return self._messages_to_openai_input(messages)

    def _merge_history_with_live_buffer(
        self,
        history: list[dict[str, Any]],
        live_buffer: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged = list(history)
        seen_uuids = {message.get("uuid") for message in merged if message.get("uuid")}
        for message in live_buffer:
            uuid = message.get("uuid")
            if uuid and uuid in seen_uuids:
                continue
            merged.append(message)
            if uuid:
                seen_uuids.add(uuid)
        return merged

    def _messages_to_openai_input(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        input_items: list[dict[str, Any]] = []
        for message in messages:
            message_type = message.get("type")
            if message_type == "user":
                text = extract_plain_user_content(message)
                if text:
                    input_items.append({"role": "user", "content": text})
            elif message_type == "assistant":
                text = self._extract_text_content(message)
                if text:
                    input_items.append({"role": "assistant", "content": text})
            elif message_type == "tool_use":
                tool_use_id = str(message.get("tool_use_id") or message.get("id") or uuid4().hex)
                name = str(message.get("name") or "")
                if not name:
                    continue
                input_items.append(
                    {
                        "type": "function_call",
                        "call_id": tool_use_id,
                        "name": name,
                        "arguments": self._json_dumps(message.get("input") or {}),
                        "status": "completed",
                    }
                )
            elif message_type == "tool_result":
                tool_use_id = str(message.get("tool_use_id") or message.get("id") or "")
                if not tool_use_id:
                    continue
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": tool_use_id,
                        "output": self._json_dumps(message.get("content")),
                    }
                )
        return input_items

    async def _consume_stream(self, managed: LiteManagedSession, events: Any, model_name: str) -> str:
        iterator = events.__aiter__()
        heartbeat_seconds = self._heartbeat_seconds()
        assistant_text_parts: list[str] = []

        while True:
            if managed.session_id in self._interrupt_requests:
                raise _OpenAIStreamInterrupted
            interrupt_event = self._interrupt_events.setdefault(managed.session_id, asyncio.Event())
            next_event_task = asyncio.create_task(iterator.__anext__())
            interrupt_task = asyncio.create_task(interrupt_event.wait())
            try:
                done, pending = await asyncio.wait(
                    {next_event_task, interrupt_task},
                    timeout=heartbeat_seconds,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not done:
                    for task in pending:
                        task.cancel()
                    await self._drain_cancelled(*pending)
                    raise TimeoutError(f"No response from OpenAI stream within {heartbeat_seconds:g}s")
                for task in pending:
                    task.cancel()
                await self._drain_cancelled(*pending)
                if interrupt_task in done:
                    if not next_event_task.done():
                        next_event_task.cancel()
                        await self._drain_cancelled(next_event_task)
                    raise _OpenAIStreamInterrupted
                event = next_event_task.result()
            except StopAsyncIteration:
                interrupt_task.cancel()
                await self._drain_cancelled(interrupt_task)
                break

            chunk = self._project_to_sse(managed, event, model_name)
            if chunk:
                assistant_text_parts.append(chunk)
            if managed.session_id in self._interrupt_requests:
                raise _OpenAIStreamInterrupted

        return "".join(assistant_text_parts)

    async def _drain_cancelled(self, *tasks: asyncio.Task[Any]) -> None:
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    def _project_to_sse(self, managed: LiteManagedSession, event: Any, model_name: str) -> str:
        if isinstance(event, RawResponsesStreamEvent):
            data = event.data
            if getattr(data, "type", None) == "response.output_text.delta":
                text = str(getattr(data, "delta", "") or "")
                if text:
                    managed.add_message(
                        {
                            "type": "stream_event",
                            "delta": {"type": "text_delta", "text": text},
                            "timestamp": _utc_now_iso(),
                            "uuid": uuid4().hex,
                            "provider": self.provider_id,
                            "model": model_name,
                        }
                    )
                return text
            return ""

        if not isinstance(event, RunItemStreamEvent):
            return ""

        item = event.item
        if event.name == "tool_called" and isinstance(item, ToolCallItem):
            self._append_tool_use(managed, item)
        elif event.name == "tool_output" and isinstance(item, ToolCallOutputItem):
            self._append_tool_result(managed, item)
        elif event.name == "message_output_created" and isinstance(item, MessageOutputItem):
            text = ItemHelpers.text_message_output(item).strip()
            if text:
                managed.add_message(self._assistant_message(text, model_name))
        return ""

    def _append_tool_use(self, managed: LiteManagedSession, item: ToolCallItem) -> None:
        raw_item = item.raw_item
        if getattr(raw_item, "type", None) != "function_call":
            return
        raw_args = getattr(raw_item, "arguments", "{}") or "{}"
        try:
            args = json.loads(raw_args)
        except json.JSONDecodeError:
            args = {"_raw_arguments": raw_args}
        if not isinstance(args, dict):
            args = {"_raw_arguments": args}

        managed.add_message(
            {
                "type": "tool_use",
                "tool_use_id": getattr(raw_item, "call_id", "") or getattr(raw_item, "id", "") or uuid4().hex,
                "name": getattr(raw_item, "name", ""),
                "input": args,
                "timestamp": _utc_now_iso(),
                "uuid": uuid4().hex,
                "provider": self.provider_id,
            }
        )

    def _append_tool_result(self, managed: LiteManagedSession, item: ToolCallOutputItem) -> None:
        output = item.output
        raw_item = item.raw_item
        call_id = ""
        if isinstance(raw_item, dict):
            call_id = str(raw_item.get("call_id") or "")
        else:
            call_id = str(getattr(raw_item, "call_id", "") or "")
        managed.add_message(
            {
                "type": "tool_result",
                "tool_use_id": call_id,
                "content": output,
                "is_error": isinstance(output, dict) and "error" in output,
                "timestamp": _utc_now_iso(),
                "uuid": uuid4().hex,
                "provider": self.provider_id,
            }
        )

    def _assistant_message(self, text: str, model_name: str) -> dict[str, Any]:
        return {
            "type": "assistant",
            "content": [{"type": "text", "text": text}],
            "timestamp": _utc_now_iso(),
            "uuid": uuid4().hex,
            "provider": self.provider_id,
            "model": model_name,
        }

    async def _emit_success(self, managed: LiteManagedSession, model_name: str) -> None:
        managed.status = "completed"
        await self._meta_store.update_status(managed.session_id, "completed")
        managed.add_message(
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "timestamp": _utc_now_iso(),
                "provider": self.provider_id,
                "model": model_name,
            }
        )
        managed.add_message(self._build_runtime_status_message(managed.session_id, managed.status))

    async def _emit_interrupted(self, managed: LiteManagedSession) -> None:
        managed.status = "interrupted"
        await self._meta_store.update_status(managed.session_id, "interrupted")
        managed.add_message(
            {
                "type": "result",
                "subtype": "error_interrupt",
                "is_error": True,
                "timestamp": _utc_now_iso(),
                "provider": self.provider_id,
            }
        )
        managed.add_message(self._build_runtime_status_message(managed.session_id, managed.status))

    async def _emit_error(
        self,
        managed: LiteManagedSession,
        subtype: str,
        error: str,
        *,
        model_name: str | None = None,
    ) -> None:
        managed.status = "error"
        await self._meta_store.update_status(managed.session_id, "error")
        message = {
            "type": "result",
            "subtype": subtype,
            "is_error": True,
            "timestamp": _utc_now_iso(),
            "provider": self.provider_id,
            "error": error,
        }
        if model_name:
            message["model"] = model_name
        managed.add_message(message)
        managed.add_message(self._build_runtime_status_message(managed.session_id, managed.status))

    async def interrupt_session(self, session_id: str) -> str:
        managed = self._sessions.get(session_id)
        if managed is None:
            meta = await self._meta_store.get(session_id)
            if meta is None:
                raise FileNotFoundError(f"session not found: {session_id}")
            return meta.status
        if managed.generation_task and not managed.generation_task.done():
            self._interrupt_requests.add(session_id)
            self._interrupt_events.setdefault(session_id, asyncio.Event()).set()
            managed.status = "interrupted"
            await self._meta_store.update_status(session_id, "interrupted")
            return "interrupted"
        return managed.status

    def _heartbeat_seconds(self) -> float:
        raw = os.getenv("ASSISTANT_STREAM_HEARTBEAT_SECONDS", "300")
        try:
            return max(float(raw), 0.001)
        except ValueError:
            return 300.0

    def _has_assistant_message(self, managed: LiteManagedSession) -> bool:
        return any(message.get("type") == "assistant" for message in managed.message_buffer)

    def _extract_text_content(self, message: dict[str, Any]) -> str | None:
        content = message.get("content")
        if isinstance(content, str):
            return content.strip() or None
        if not isinstance(content, list):
            return None
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") not in {"text", None}:
                continue
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
        if not parts:
            return None
        return "\n".join(parts)

    def _json_dumps(self, value: Any) -> str:
        return json.dumps(value, ensure_ascii=False)
