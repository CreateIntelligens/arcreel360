"""Assistant runtime provider abstractions and adapters."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, Awaitable, Callable
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel

from server.agent_runtime.models import SessionMeta, SessionStatus
from server.agent_runtime.sdk_transcript_adapter import SdkTranscriptAdapter
from server.agent_runtime.session_identity import infer_provider_id, runtime_session_id
from server.agent_runtime.session_manager import SessionManager

AssistantProviderTier = Literal["lite", "workflow-grade", "full"]
AssistantPrompt = str | AsyncIterable[dict[str, Any]]


class AssistantProviderCapabilities(BaseModel):
    """Normalized capability matrix exposed by a runtime provider."""

    provider: str
    tier: AssistantProviderTier
    supports_streaming: bool = True
    supports_images: bool = False
    supports_tool_calls: bool = False
    supports_interrupt: bool = False
    supports_resume: bool = False
    supports_subagents: bool = False
    supports_permission_hooks: bool = False


class UnsupportedCapabilityError(RuntimeError):
    """Raised when a provider is asked to do something outside its capability set."""

    def __init__(self, provider_id: str, capability: str, detail: str | None = None):
        self.provider_id = provider_id
        self.capability = capability
        self.detail = detail or f"provider '{provider_id}' does not support capability '{capability}'"
        super().__init__(self.detail)

    def as_detail(self) -> dict[str, str]:
        return {
            "error": "unsupported_capability",
            "provider": self.provider_id,
            "capability": self.capability,
            "detail": self.detail,
        }


class ProviderUnavailableError(RuntimeError):
    """Raised when the configured provider is missing or not registered."""

    def __init__(self, provider_id: str):
        self.provider_id = provider_id
        super().__init__(f"assistant provider '{provider_id}' is not available")


@runtime_checkable
class AssistantRuntimeProvider(Protocol):
    """Provider-agnostic runtime contract used by AssistantService."""

    @property
    def provider_id(self) -> str: ...

    @property
    def capabilities(self) -> AssistantProviderCapabilities: ...

    async def send_new_session(
        self,
        project_name: str,
        prompt: AssistantPrompt,
        *,
        echo_text: str | None = None,
        echo_content: list[dict[str, Any]] | None = None,
    ) -> str: ...

    async def send_message(
        self,
        session_id: str,
        prompt: AssistantPrompt,
        *,
        echo_text: str | None = None,
        echo_content: list[dict[str, Any]] | None = None,
        meta: SessionMeta | None = None,
    ) -> None: ...

    async def interrupt_session(self, session_id: str) -> SessionStatus: ...

    async def close_session(self, session_id: str, *, reason: str = "session closed") -> None: ...

    async def answer_user_question(
        self,
        session_id: str,
        question_id: str,
        answers: dict[str, str],
    ) -> None: ...

    async def subscribe(self, session_id: str, replay_buffer: bool = True) -> asyncio.Queue: ...

    async def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None: ...

    async def get_status(self, session_id: str) -> SessionStatus | None: ...

    def get_live_status(self, session_id: str) -> SessionStatus | None: ...

    def has_live_session(self, session_id: str) -> bool: ...

    def get_buffered_messages(self, session_id: str) -> list[dict[str, Any]]: ...

    async def read_history_messages(self, session_id: str) -> list[dict[str, Any]]: ...

    async def get_pending_questions_snapshot(self, session_id: str) -> list[dict[str, Any]]: ...

    async def shutdown_gracefully(self, timeout: float = 30.0) -> None: ...


class ClaudeRuntimeProvider:
    """Adapter that exposes the existing Claude SessionManager via the provider contract."""

    def __init__(self, session_manager: SessionManager):
        self._session_manager = session_manager
        self._transcript_adapter = SdkTranscriptAdapter()
        self._capabilities = AssistantProviderCapabilities(
            provider="claude",
            tier="full",
            supports_streaming=True,
            supports_images=True,
            supports_tool_calls=True,
            supports_interrupt=True,
            supports_resume=True,
            supports_subagents=True,
            supports_permission_hooks=True,
        )

    @property
    def provider_id(self) -> str:
        return self._capabilities.provider

    @property
    def capabilities(self) -> AssistantProviderCapabilities:
        return self._capabilities

    async def send_new_session(
        self,
        project_name: str,
        prompt: AssistantPrompt,
        *,
        echo_text: str | None = None,
        echo_content: list[dict[str, Any]] | None = None,
    ) -> str:
        return await self._session_manager.send_new_session(
            project_name,
            prompt,
            echo_text=echo_text,
            echo_content=echo_content,
        )

    async def send_message(
        self,
        session_id: str,
        prompt: AssistantPrompt,
        *,
        echo_text: str | None = None,
        echo_content: list[dict[str, Any]] | None = None,
        meta: SessionMeta | None = None,
    ) -> None:
        await self._session_manager.send_message(
            session_id,
            prompt,
            echo_text=echo_text,
            echo_content=echo_content,
            meta=meta,
        )

    async def interrupt_session(self, session_id: str) -> SessionStatus:
        return await self._session_manager.interrupt_session(session_id)

    async def close_session(self, session_id: str, *, reason: str = "session closed") -> None:
        await self._session_manager.close_session(session_id, reason=reason)

    async def answer_user_question(
        self,
        session_id: str,
        question_id: str,
        answers: dict[str, str],
    ) -> None:
        await self._session_manager.answer_user_question(session_id, question_id, answers)

    async def subscribe(self, session_id: str, replay_buffer: bool = True) -> asyncio.Queue:
        return await self._session_manager.subscribe(session_id, replay_buffer=replay_buffer)

    async def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        await self._session_manager.unsubscribe(session_id, queue)

    async def get_status(self, session_id: str) -> SessionStatus | None:
        return await self._session_manager.get_status(session_id)

    def get_live_status(self, session_id: str) -> SessionStatus | None:
        managed = self._session_manager.sessions.get(session_id)
        return managed.status if managed is not None else None

    def has_live_session(self, session_id: str) -> bool:
        return session_id in self._session_manager.sessions

    def get_buffered_messages(self, session_id: str) -> list[dict[str, Any]]:
        return self._session_manager.get_buffered_messages(session_id)

    async def read_history_messages(self, session_id: str) -> list[dict[str, Any]]:
        sdk_session_id = runtime_session_id(session_id)
        return await asyncio.to_thread(self._transcript_adapter.read_raw_messages, sdk_session_id)

    async def get_pending_questions_snapshot(self, session_id: str) -> list[dict[str, Any]]:
        return await self._session_manager.get_pending_questions_snapshot(session_id)

    def start_patrol(self) -> None:
        self._session_manager.start_patrol()

    async def shutdown_gracefully(self, timeout: float = 30.0) -> None:
        await self._session_manager.shutdown_gracefully(timeout=timeout)


class RoutingRuntimeProvider:
    """Dispatch runtime operations to the provider owning a session or active provider."""

    def __init__(
        self,
        providers: dict[str, AssistantRuntimeProvider],
        active_provider_resolver: Callable[[], Awaitable[str]],
    ):
        self._providers = providers
        self._active_provider_resolver = active_provider_resolver
        self._capabilities = AssistantProviderCapabilities(provider="router", tier="workflow-grade")

    @property
    def provider_id(self) -> str:
        return self._capabilities.provider

    @property
    def capabilities(self) -> AssistantProviderCapabilities:
        return self._capabilities

    async def _resolve_active_provider(self) -> AssistantRuntimeProvider:
        provider_id = await self._active_provider_resolver()
        provider = self._providers.get(provider_id)
        if provider is None:
            raise ProviderUnavailableError(provider_id)
        return provider

    def _provider_for_session(self, session_id: str) -> AssistantRuntimeProvider:
        provider_id = infer_provider_id(session_id)
        provider = self._providers.get(provider_id)
        if provider is None:
            raise ProviderUnavailableError(provider_id)
        return provider

    async def send_new_session(
        self,
        project_name: str,
        prompt: AssistantPrompt,
        *,
        echo_text: str | None = None,
        echo_content: list[dict[str, Any]] | None = None,
    ) -> str:
        provider = await self._resolve_active_provider()
        return await provider.send_new_session(
            project_name,
            prompt,
            echo_text=echo_text,
            echo_content=echo_content,
        )

    async def send_message(
        self,
        session_id: str,
        prompt: AssistantPrompt,
        *,
        echo_text: str | None = None,
        echo_content: list[dict[str, Any]] | None = None,
        meta: SessionMeta | None = None,
    ) -> None:
        provider = self._provider_for_session(session_id)
        await provider.send_message(
            session_id,
            prompt,
            echo_text=echo_text,
            echo_content=echo_content,
            meta=meta,
        )

    async def interrupt_session(self, session_id: str) -> SessionStatus:
        return await self._provider_for_session(session_id).interrupt_session(session_id)

    async def close_session(self, session_id: str, *, reason: str = "session closed") -> None:
        await self._provider_for_session(session_id).close_session(session_id, reason=reason)

    async def answer_user_question(
        self,
        session_id: str,
        question_id: str,
        answers: dict[str, str],
    ) -> None:
        await self._provider_for_session(session_id).answer_user_question(session_id, question_id, answers)

    async def subscribe(self, session_id: str, replay_buffer: bool = True) -> asyncio.Queue:
        return await self._provider_for_session(session_id).subscribe(session_id, replay_buffer=replay_buffer)

    async def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        await self._provider_for_session(session_id).unsubscribe(session_id, queue)

    async def get_status(self, session_id: str) -> SessionStatus | None:
        return await self._provider_for_session(session_id).get_status(session_id)

    def get_live_status(self, session_id: str) -> SessionStatus | None:
        return self._provider_for_session(session_id).get_live_status(session_id)

    def has_live_session(self, session_id: str) -> bool:
        try:
            return self._provider_for_session(session_id).has_live_session(session_id)
        except ProviderUnavailableError:
            return False

    def get_buffered_messages(self, session_id: str) -> list[dict[str, Any]]:
        return self._provider_for_session(session_id).get_buffered_messages(session_id)

    async def read_history_messages(self, session_id: str) -> list[dict[str, Any]]:
        return await self._provider_for_session(session_id).read_history_messages(session_id)

    async def get_pending_questions_snapshot(self, session_id: str) -> list[dict[str, Any]]:
        return await self._provider_for_session(session_id).get_pending_questions_snapshot(session_id)

    def start_patrol(self) -> None:
        for provider in self._providers.values():
            start_patrol = getattr(provider, "start_patrol", None)
            if callable(start_patrol):
                start_patrol()

    async def shutdown_gracefully(self, timeout: float = 30.0) -> None:
        for provider in self._providers.values():
            await provider.shutdown_gracefully(timeout=timeout)
