"""ManagedSession and related types for the Claude SDK session lifecycle.

Extracted from ``session_manager.py``: ``ManagedSession`` models a single
managed ClaudeSDKClient session with its message buffer, subscriber fan-out and
pending AskUserQuestion bookkeeping, while ``SessionManager`` (still in
``session_manager.py``) owns the cross-session lifecycle.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from server.agent_runtime.models import SessionStatus


class SessionCapacityError(Exception):
    """所有併發槽位已被 running 會話佔滿，無法建立新連線。"""

    pass


@dataclass
class PendingQuestion:
    """Tracks a pending AskUserQuestion request."""

    question_id: str
    payload: dict[str, Any]
    answer_future: asyncio.Future[dict[str, str]]


class PendingQuestionMixin:
    """AskUserQuestion bookkeeping shared across managed-session variants.

    Expects the host class to declare ``pending_questions: dict[str, PendingQuestion]``.
    """

    pending_questions: dict[str, PendingQuestion]

    def add_pending_question(self, payload: dict[str, Any]) -> PendingQuestion:
        """Register a pending AskUserQuestion payload (copied so callers keep ownership)."""
        question_payload = dict(payload)
        question_id = str(question_payload.get("question_id") or f"aq_{uuid4().hex}")
        question_payload["question_id"] = question_id
        future: asyncio.Future[dict[str, str]] = asyncio.get_running_loop().create_future()
        pending = PendingQuestion(
            question_id=question_id,
            payload=question_payload,
            answer_future=future,
        )
        self.pending_questions[question_id] = pending
        return pending

    def resolve_pending_question(self, question_id: str, answers: dict[str, str]) -> bool:
        """Resolve a pending AskUserQuestion with user answers."""
        pending = self.pending_questions.pop(question_id, None)
        if pending is None:
            return False
        if not pending.answer_future.done():
            pending.answer_future.set_result(answers)
        return True

    def cancel_pending_questions(self, reason: str = "session closed") -> None:
        """Cancel all pending AskUserQuestion waiters."""
        for pending in list(self.pending_questions.values()):
            if not pending.answer_future.done():
                pending.answer_future.set_exception(RuntimeError(reason))
        self.pending_questions.clear()

    def get_pending_question_payloads(self) -> list[dict[str, Any]]:
        """Return unresolved AskUserQuestion payloads for reconnect snapshot."""
        return [pending.payload for pending in self.pending_questions.values()]


@dataclass
class ManagedSession(PendingQuestionMixin):
    """A managed ClaudeSDKClient session."""

    session_id: str  # sdk_session_id（已有會話）或臨時 UUID（新會話等待中）
    client: Any  # ClaudeSDKClient
    status: SessionStatus = "idle"
    project_name: str = ""  # 用於 _register_new_session
    sdk_id_event: asyncio.Event = field(default_factory=asyncio.Event)
    resolved_sdk_id: str | None = None  # consumer 設定，send_new_session 讀取
    message_buffer: list[dict[str, Any]] = field(default_factory=list)
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    consumer_task: asyncio.Task | None = None
    buffer_max_size: int = 100
    pending_questions: dict[str, PendingQuestion] = field(default_factory=dict)
    pending_user_echoes: list[str] = field(default_factory=list)
    interrupt_requested: bool = False
    last_activity: float | None = None  # updated on every send/receive
    _cleanup_task: asyncio.Task | None = None  # current cleanup timer (idle TTL or terminal delay)

    # Message types that must never be silently dropped from subscriber queues.
    _CRITICAL_MESSAGE_TYPES = {"result", "runtime_status", "user", "assistant"}
    # Transient types that are evicted first when buffer is full.
    _TRANSIENT_BUFFER_TYPES = {"stream_event"}

    def add_message(self, message: dict[str, Any]) -> None:
        """Add message to buffer and notify subscribers."""
        self.message_buffer.append(message)
        if len(self.message_buffer) > self.buffer_max_size:
            self._evict_oldest_buffer_entry()
        self._broadcast_to_subscribers(message)

    def _evict_oldest_buffer_entry(self) -> None:
        """Evict one entry from buffer, preferring transient stream_events."""
        for i, m in enumerate(self.message_buffer[:-1]):
            if m.get("type") in self._TRANSIENT_BUFFER_TYPES:
                self.message_buffer.pop(i)
                return
        self.message_buffer.pop(0)

    def _broadcast_to_subscribers(self, message: dict[str, Any]) -> None:
        """Push message to all subscriber queues, evicting non-critical on overflow."""
        is_critical = message.get("type") in self._CRITICAL_MESSAGE_TYPES
        stale_queues: list[asyncio.Queue] = []
        for queue in self.subscribers:
            if not self._try_enqueue(queue, message, is_critical):
                stale_queues.append(queue)
        for q in stale_queues:
            # Drain the hopelessly full queue and inject a reconnect signal so
            # the SSE consumer loop terminates instead of blocking forever.
            self._drain_and_signal_reconnect(q)
            self.subscribers.discard(q)

    def _drain_and_signal_reconnect(self, queue: asyncio.Queue) -> None:
        """Empty *queue* and push a reconnect signal so the SSE loop exits.

        Uses a connection-level ``_queue_overflow`` type rather than
        ``runtime_status`` so the SSE consumer can close the stream without
        misrepresenting the session's actual status to the client.
        """
        while not queue.empty():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        try:
            queue.put_nowait(
                {
                    "type": "_queue_overflow",
                    "session_id": self.session_id,
                }
            )
        except asyncio.QueueFull:
            pass  # should never happen after drain

    def _try_enqueue(self, queue: asyncio.Queue, message: dict[str, Any], is_critical: bool) -> bool:
        """Try to put *message* into *queue*. Returns False if the queue should be discarded."""
        try:
            queue.put_nowait(message)
            return True
        except asyncio.QueueFull:
            if not is_critical:
                return True  # non-critical drop is acceptable
        # Critical message on a full queue — evict one non-critical to make room.
        self._evict_non_critical(queue)
        try:
            queue.put_nowait(message)
            return True
        except asyncio.QueueFull:
            return False

    @staticmethod
    def _evict_non_critical(queue: asyncio.Queue) -> bool:
        """Try to remove one non-critical message from *queue* to make room."""
        temp: list[dict[str, Any]] = []
        evicted = False
        while not queue.empty():
            try:
                msg = queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if not evicted and msg.get("type") not in ManagedSession._CRITICAL_MESSAGE_TYPES:
                evicted = True  # drop this one
                continue
            temp.append(msg)
        for msg in temp:
            try:
                queue.put_nowait(msg)
            except asyncio.QueueFull:
                break
        return evicted

    def clear_buffer(self) -> None:
        """Clear message buffer after session completes."""
        self.message_buffer.clear()
