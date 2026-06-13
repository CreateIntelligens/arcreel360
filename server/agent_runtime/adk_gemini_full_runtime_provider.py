"""ADK-backed Gemini Full Runtime Provider."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from google.adk.agents.llm_agent import LlmAgent
from google.adk.events.event import Event
from google.adk.models import Gemini
from google.adk.runners import Runner
from google.genai import types as genai_types

from lib.db import async_session_factory
from lib.project_manager import ProjectManager
from server.agent_runtime.adk_session_service import AgentMessagesSessionService
from server.agent_runtime.adk_tool_adapters import ALL_TOOLS
from server.agent_runtime.permission_gate import PermissionGate, as_adk_callback, get_default_gate
from server.agent_runtime.runtime_provider import (
    AssistantPrompt,
    AssistantProviderCapabilities,
)
from server.agent_runtime.session_identity import GEMINI_FULL_PROVIDER_ID, build_external_session_id
from server.agent_runtime.session_store import SessionMetaStore
from server.agent_runtime.skill_function_declarations import SkillCallContext
from server.agent_runtime.text_backend_runtime_provider import (
    BaseTextBackendRuntimeProvider,
    LiteManagedSession,
)
from server.agent_runtime.tool_sandbox import ToolSandbox

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _log_task_exception(task: asyncio.Task[Any]) -> None:
    """fire-and-forget task done callback:把例外 log 出來,別讓它消失。"""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.warning("background task failed: %s", exc, exc_info=exc)


def make_gemini_model(client: Any, model_name: str) -> Gemini:
    """Creates a Gemini model subclass that injects our pre-configured client."""

    class InjectedGemini(Gemini):
        @property
        def api_client(self):
            return client

        @property
        def _live_api_client(self):
            return client

    return InjectedGemini(model=model_name)


class AdkGeminiFullRuntimeProvider(BaseTextBackendRuntimeProvider):
    """Full-tier provider implemented via Google Gen AI Agent Development Kit."""

    def __init__(
        self,
        *,
        project_root: Path,
        data_dir: Path,
        meta_store: SessionMetaStore,
        permission_gate: PermissionGate | None = None,
        max_tool_turns: int = 20,
    ):
        super().__init__(
            provider_id=GEMINI_FULL_PROVIDER_ID,
            capabilities=AssistantProviderCapabilities(
                provider=GEMINI_FULL_PROVIDER_ID,
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
        self._client_cache: tuple[tuple, Any, str] | None = None
        # 持有 fire-and-forget DB 更新 task 的引用,避免被 GC 提早回收
        self._pending_status_tasks: set[asyncio.Task[Any]] = set()

    def _spawn_status_update(self, session_id: str, status: str) -> None:
        """非同步更新 session status,失敗時 log 而不是吞掉。"""
        task = asyncio.create_task(self._meta_store.update_status(session_id, status))
        self._pending_status_tasks.add(task)
        task.add_done_callback(self._pending_status_tasks.discard)
        task.add_done_callback(_log_task_exception)

    async def _create_backend(self, project_name: str) -> Any:
        return None

    async def _get_genai_client(self) -> tuple[Any, str]:
        """Resolves config and creates google.genai.Client, just like legacy provider."""
        from google import genai

        resolver = self._resolver
        async with resolver.session() as r:
            provider_id, model_id = await r.default_text_backend()
            aistudio = await r.provider_config("gemini-aistudio")

        api_key = (aistudio or {}).get("api_key")
        base_url = (aistudio or {}).get("base_url") or None
        model = model_id or "gemini-2.5-pro"
        cache_key = (provider_id, model_id, api_key, base_url)

        if self._client_cache is not None and self._client_cache[0] == cache_key:
            return self._client_cache[1], self._client_cache[2]

        if provider_id == "gemini-vertex":
            from google.oauth2 import service_account

            from lib.system_config import resolve_vertex_credentials_path

            cred_file = resolve_vertex_credentials_path(self._project_root)
            if cred_file is None:
                raise RuntimeError("未找到 Vertex AI 凭证；请将服务账号 JSON 放入 vertex_keys/")

            def _load_vertex_client():
                import json as _json

                with open(cred_file) as f:
                    proj_id = _json.load(f).get("project_id")
                creds = service_account.Credentials.from_service_account_file(
                    str(cred_file),
                    scopes=("https://www.googleapis.com/auth/cloud-platform",),
                )
                return genai.Client(vertexai=True, project=proj_id, location="global", credentials=creds)

            client = await asyncio.to_thread(_load_vertex_client)
        else:
            if not api_key:
                raise RuntimeError("Gemini AI Studio 未配置 API key；请在 /settings 设定")
            http_options = {"base_url": base_url} if base_url else None
            client = genai.Client(api_key=api_key, http_options=http_options)

        self._client_cache = (cache_key, client, model)
        return client, model

    async def send_new_session(
        self,
        project_name: str,
        prompt: AssistantPrompt,
        *,
        echo_text: str | None = None,
        echo_content: list[dict[str, Any]] | None = None,
    ) -> str:
        session_id = build_external_session_id(self.provider_id, uuid4().hex)
        await self._meta_store.create(project_name, session_id)

        # We set persist_callback=None because AgentMessagesSessionService handles DB writes
        managed = LiteManagedSession(
            session_id=session_id,
            project_name=project_name,
            persist_callback=None,
        )
        self._sessions[session_id] = managed

        await self._start_generation(managed, prompt, echo_text=echo_text, echo_content=echo_content)
        return session_id

    async def send_message(
        self,
        session_id: str,
        prompt: AssistantPrompt,
        *,
        echo_text: str | None = None,
        echo_content: list[dict[str, Any]] | None = None,
        meta: Any | None = None,
    ) -> None:
        managed = self._sessions.get(session_id)
        if managed is None:
            existing = meta or await self._meta_store.get(session_id)
            if existing is None:
                raise FileNotFoundError(f"session not found: {session_id}")
            project_name = (
                existing.project_name
                if hasattr(existing, "project_name")
                else (existing.get("project_name", "") if isinstance(existing, dict) else "")
            )
            # Set persist_callback=None here as well
            managed = LiteManagedSession(
                session_id=session_id,
                project_name=project_name,
                persist_callback=None,
            )
            self._sessions[session_id] = managed
        await self._start_generation(managed, prompt, echo_text=echo_text, echo_content=echo_content)

    def _emit_error(self, managed: LiteManagedSession, subtype: str, error: str) -> None:
        managed.status = "error"
        managed.add_message(
            {
                "type": "result",
                "subtype": subtype,
                "is_error": True,
                "timestamp": _utc_now_iso(),
                "provider": self.provider_id,
                "error": error,
            }
        )
        managed.add_message(self._build_runtime_status_message(managed.session_id, managed.status))

        self._spawn_status_update(managed.session_id, "error")

    def _emit_success(self, managed: LiteManagedSession, model_name: str) -> None:
        managed.status = "completed"
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

        self._spawn_status_update(managed.session_id, "completed")

    async def _run_generation(
        self,
        managed: LiteManagedSession,
        prompt: AssistantPrompt,
        *,
        echo_text: str | None,
        echo_content: list[dict[str, Any]] | None,
    ) -> None:
        try:
            client, model_name = await self._get_genai_client()
        except Exception as exc:
            logger.exception("adk-gemini-full: client init failed")
            self._emit_error(managed, "config_error", str(exc))
            return

        prompt_text = self._extract_prompt_text(prompt, echo_text, echo_content)

        sandbox = ToolSandbox(
            project_root=self._project_root / "projects",
            project_name=managed.project_name,
        )
        skill_ctx = SkillCallContext(
            project_name=managed.project_name,
            sandbox=sandbox,
            project_manager=self._project_manager,
            session_id=managed.session_id,
            approval_requester=lambda payload: self._request_approval(managed, payload),
        )

        model = make_gemini_model(client, model_name)
        agent = LlmAgent(
            name="gemini_full_agent",
            model=model,
            tools=ALL_TOOLS,
            before_tool_callback=as_adk_callback(self._permission_gate),
            instruction=self._build_system_prompt(managed.project_name),
        )

        # Create a new session service specifically bound to this project and using async DB
        session_service = AgentMessagesSessionService(
            project_name=managed.project_name, session_factory=async_session_factory
        )

        # Runner 需要 app_name 在建構時注入(非 run_async 引數);ADK 內部會用此 app_name
        # 在 session_service 上做 lookup,所以與 session_service.create_session 時的
        # app_name 必須一致。
        runner = Runner(
            agent=agent,
            app_name="arcreel",
            session_service=session_service,
        )

        # Ensure ADK Session 存在(沿用既有 session_id;若已建過 get_session 會回傳)。
        # state 用來傳 skill_ctx 給 SkillBaseTool.run_async() 透過 tool_context.state 取用。
        existing = await session_service.get_session(
            app_name="arcreel",
            user_id="default_user",
            session_id=managed.session_id,
        )
        if existing is None:
            await session_service.create_session(
                app_name="arcreel",
                user_id="default_user",
                session_id=managed.session_id,
                state={"skill_ctx": skill_ctx},
            )

        import os

        heartbeat = int(os.getenv("ASSISTANT_STREAM_HEARTBEAT_SECONDS", "300"))

        try:
            full_text = ""
            new_message = genai_types.Content(
                role="user",
                parts=[genai_types.Part(text=prompt_text)],
            )
            gen = runner.run_async(
                user_id="default_user",
                session_id=managed.session_id,
                new_message=new_message,
                state_delta={"skill_ctx": skill_ctx},
            )

            while True:
                try:
                    event = await asyncio.wait_for(gen.__anext__(), timeout=heartbeat)
                except StopAsyncIteration:
                    break
                except TimeoutError:
                    raise TimeoutError(f"No response from ADK stream within {heartbeat}s")

                text_chunk = self._project_to_sse(managed, event, model_name)
                if text_chunk:
                    full_text += text_chunk

            if full_text.strip():
                managed.add_message(
                    {
                        "type": "assistant",
                        "content": [{"type": "text", "text": full_text.strip()}],
                        "timestamp": _utc_now_iso(),
                        "uuid": uuid4().hex,
                        "provider": self.provider_id,
                        "model": model_name,
                    }
                )

            self._emit_success(managed, model_name)
        except asyncio.CancelledError:
            managed.status = "interrupted"
            self._spawn_status_update(managed.session_id, "interrupted")
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
            raise
        except Exception as exc:
            logger.exception("adk-gemini-full: generation failed session=%s", managed.session_id)
            self._emit_error(managed, "generation_failed", str(exc))
        finally:
            managed.generation_task = None

    def _project_to_sse(self, managed: LiteManagedSession, event: Event, model_name: str) -> str:
        """Projects ADK Event back to legacy SSE message format.
        Returns any extracted text chunk.
        """
        # Process tool calls/responses regardless of author
        if function_calls := event.get_function_calls():
            for func_call in function_calls:
                managed.add_message(
                    {
                        "type": "tool_use",
                        "tool_use_id": func_call.id or str(uuid4().hex),
                        "name": func_call.name,
                        "input": func_call.args,
                        "timestamp": _utc_now_iso(),
                        "uuid": uuid4().hex,
                        "provider": self.provider_id,
                    }
                )

        if function_responses := event.get_function_responses():
            for func_res in function_responses:
                managed.add_message(
                    {
                        "type": "tool_result",
                        "tool_use_id": func_res.id or "",
                        "content": func_res.response,
                        "is_error": isinstance(func_res.response, dict) and "error" in func_res.response,
                        "timestamp": _utc_now_iso(),
                        "uuid": uuid4().hex,
                        "provider": self.provider_id,
                    }
                )

        if event.author == "user":
            return ""

        text = ""
        if event.content and event.content.parts:
            for part in event.content.parts:
                if getattr(part, "text", None):
                    text += part.text

        if text:
            managed.add_message(
                {
                    "type": "stream_event",
                    "delta": {"type": "text_delta", "text": text},
                    "timestamp": _utc_now_iso(),
                    "uuid": uuid4().hex,
                    "provider": self.provider_id,
                }
            )

        return text
