"""Agent runtime data models."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from server.agent_runtime.session_identity import infer_provider_id

SessionStatus = Literal["idle", "running", "completed", "error", "interrupted"]


class SessionMeta(BaseModel):
    """Session metadata stored in database."""

    id: str  # 對外暴露，填充 sdk_session_id 值
    provider: str = "claude"
    project_name: str
    title: str = ""
    status: SessionStatus = "idle"
    created_at: datetime
    updated_at: datetime
    capabilities: dict[str, Any] | None = None

    @classmethod
    def from_store(cls, **data: Any) -> "SessionMeta":
        session_id = str(data.get("id") or "")
        return cls(
            **{
                **data,
                "provider": data.get("provider") or infer_provider_id(session_id),
            }
        )


class AssistantSnapshotV2(BaseModel):
    """Unified assistant snapshot for history and reconnect."""

    session_id: str
    status: SessionStatus
    turns: list[dict[str, Any]]
    draft_turn: dict[str, Any] | None = None
    pending_questions: list[dict[str, Any]] = Field(default_factory=list)
