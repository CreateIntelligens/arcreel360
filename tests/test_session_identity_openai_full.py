"""OpenAI full-tier session identity routing tests."""

from __future__ import annotations

from server.agent_runtime.session_identity import (
    OPENAI_FULL_PROVIDER_ID,
    OPENAI_LITE_PROVIDER_ID,
    build_external_session_id,
    infer_provider_id,
    runtime_session_id,
)


def test_openai_full_prefix_routes_to_full_provider() -> None:
    session_id = build_external_session_id(OPENAI_FULL_PROVIDER_ID, "a" * 32)

    assert session_id == "openai-full:" + "a" * 32
    assert infer_provider_id(session_id) == OPENAI_FULL_PROVIDER_ID
    assert runtime_session_id(session_id) == "a" * 32


def test_openai_lite_prefix_still_routes_to_lite_provider() -> None:
    assert infer_provider_id("openai:abc123") == OPENAI_LITE_PROVIDER_ID
    assert runtime_session_id("openai:abc123") == "abc123"
