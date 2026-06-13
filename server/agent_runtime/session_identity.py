"""Helpers for external assistant session IDs across multiple providers."""

from __future__ import annotations

CLAUDE_PROVIDER_ID = "claude"
GEMINI_LITE_PROVIDER_ID = "gemini-lite"
GEMINI_FULL_PROVIDER_ID = "gemini-full"
OPENAI_LITE_PROVIDER_ID = "openai-lite"
OPENAI_FULL_PROVIDER_ID = "openai-full"

# 前缀越长越要先匹配（split 时按 ":" 第一個段命中），
# 因此 `gemini-full` 必须在 `gemini` 之前，否则 `gemini-full:xxx` 会被误识为 lite。
_PROVIDER_TO_PREFIX = {
    GEMINI_FULL_PROVIDER_ID: "gemini-full",
    GEMINI_LITE_PROVIDER_ID: "gemini",
    OPENAI_FULL_PROVIDER_ID: "openai-full",
    OPENAI_LITE_PROVIDER_ID: "openai",
}
_PREFIX_TO_PROVIDER = {prefix: provider for provider, prefix in _PROVIDER_TO_PREFIX.items()}


def build_external_session_id(provider_id: str, runtime_session_id: str) -> str:
    """Build an externally visible session ID for a provider-local session ID."""
    prefix = _PROVIDER_TO_PREFIX.get(provider_id)
    if not prefix:
        return runtime_session_id
    return f"{prefix}:{runtime_session_id}"


def split_external_session_id(session_id: str) -> tuple[str, str]:
    """Return (provider_id, runtime_session_id) for an external session ID."""
    if ":" not in session_id:
        return CLAUDE_PROVIDER_ID, session_id

    prefix, runtime_session_id = session_id.split(":", 1)
    provider_id = _PREFIX_TO_PROVIDER.get(prefix)
    if provider_id is None or not runtime_session_id:
        return CLAUDE_PROVIDER_ID, session_id
    return provider_id, runtime_session_id


def infer_provider_id(session_id: str) -> str:
    """Infer provider ID from an external session ID."""
    provider_id, _ = split_external_session_id(session_id)
    return provider_id


def runtime_session_id(session_id: str) -> str:
    """Extract the provider-local runtime session ID from an external session ID."""
    _, raw_session_id = split_external_session_id(session_id)
    return raw_session_id
