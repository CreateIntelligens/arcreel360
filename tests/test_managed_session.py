"""Tests for the extracted ManagedSession module."""

import pytest

from server.agent_runtime.managed_session import (
    ManagedSession,
    PendingQuestion,
    SessionCapacityError,
)


def test_capacity_error_is_exception():
    assert issubclass(SessionCapacityError, Exception)


def test_add_message_appends_to_buffer():
    s = ManagedSession(session_id="s1", client=None)
    s.add_message({"type": "assistant", "text": "hi"})
    assert s.message_buffer[-1]["text"] == "hi"


def test_buffer_eviction_prefers_transient_stream_events():
    s = ManagedSession(session_id="s1", client=None, buffer_max_size=2)
    s.add_message({"type": "stream_event", "n": 1})
    s.add_message({"type": "assistant", "n": 2})
    # Adding a third entry triggers eviction; the transient stream_event goes first.
    s.add_message({"type": "result", "n": 3})
    types = [m["type"] for m in s.message_buffer]
    assert "stream_event" not in types
    assert types == ["assistant", "result"]


async def test_pending_question_lifecycle():
    s = ManagedSession(session_id="s1", client=None)
    pending = s.add_pending_question({"question_id": "q1", "questions": []})
    assert isinstance(pending, PendingQuestion)
    assert pending.question_id == "q1"
    assert "q1" in s.pending_questions

    resolved = s.resolve_pending_question("q1", {"a": "b"})
    assert resolved is True
    assert "q1" not in s.pending_questions
    assert await pending.answer_future == {"a": "b"}


async def test_resolve_unknown_question_returns_false():
    s = ManagedSession(session_id="s1", client=None)
    assert s.resolve_pending_question("missing", {}) is False


async def test_cancel_pending_questions_sets_exception():
    s = ManagedSession(session_id="s1", client=None)
    pending = s.add_pending_question({"question_id": "q1", "questions": []})
    s.cancel_pending_questions("session closed")
    assert s.pending_questions == {}
    with pytest.raises(RuntimeError):
        await pending.answer_future


async def test_get_pending_question_payloads():
    s = ManagedSession(session_id="s1", client=None)
    s.add_pending_question({"question_id": "q1", "questions": []})
    payloads = s.get_pending_question_payloads()
    assert len(payloads) == 1
    assert payloads[0]["question_id"] == "q1"


def test_clear_buffer():
    s = ManagedSession(session_id="s1", client=None)
    s.add_message({"type": "assistant", "text": "hi"})
    s.clear_buffer()
    assert s.message_buffer == []
