"""ADK Session Service bridging to agent_messages table."""

from typing import Any
from uuid import uuid4

from google.adk.events.event import Event
from google.adk.sessions.base_session_service import BaseSessionService, GetSessionConfig, ListSessionsResponse
from google.adk.sessions.session import Session

from lib.db import safe_session_factory
from lib.db.repositories.agent_message_repo import AgentMessageRepository
from server.agent_runtime.session_identity import GEMINI_FULL_PROVIDER_ID, build_external_session_id
from server.agent_runtime.session_store import SessionMetaStore


class AgentMessagesSessionService(BaseSessionService):
    def __init__(self, project_name: str, session_factory=None):
        self.project_name = project_name
        self._session_factory = session_factory or safe_session_factory
        self._meta_store = SessionMetaStore(session_factory=self._session_factory)

    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> Session:
        sid = session_id or build_external_session_id(GEMINI_FULL_PROVIDER_ID, uuid4().hex)
        await self._meta_store.create(self.project_name, sid)
        return Session(id=sid, app_name=app_name, user_id=user_id, state=state or {})

    async def append_event(self, session: Session, event: Event) -> Event:
        # BaseService implementation takes care of temp state delta etc
        event = await super().append_event(session, event)

        # Mapping to agent_message format (may yield multiple rows, e.g. an
        # assistant text + tool_use carried in a single ADK event).
        msgs = self._event_to_dicts(event)

        async with self._session_factory() as db_session:
            repo = AgentMessageRepository(db_session)
            for msg in msgs:
                await repo.append(session.id, msg)
        return event

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: GetSessionConfig | None = None,
    ) -> Session | None:
        session = Session(id=session_id, app_name=app_name, user_id=user_id)
        events = await self.list_events(session_id)
        for e in events:
            session.events.append(e)
            self._update_session_state(session, e)
        return session

    async def list_events(self, session_id: str) -> list[Event]:
        async with self._session_factory() as db_session:
            repo = AgentMessageRepository(db_session)
            msgs = await repo.list(session_id)

        events = []
        for msg in msgs:
            # Split-off assistant text rows exist only for history rendering;
            # the full event is reconstructed from the paired tool_use row.
            if msg.get("_adk_replay_skip"):
                continue
            events.append(self._dict_to_event(msg))
        return events

    async def list_sessions(self, *, app_name: str, user_id: str | None = None) -> ListSessionsResponse:
        return ListSessionsResponse(sessions=[])

    async def delete_session(self, *, app_name: str, user_id: str, session_id: str) -> None:
        async with self._session_factory() as db_session:
            repo = AgentMessageRepository(db_session)
            await repo.delete_for_session(session_id)

    def _event_to_dicts(self, event: Event) -> list[dict[str, Any]]:
        """Convert an ADK event into one or more agent_messages dict rows.

        Most events map to a single row. When a model event carries *both*
        assistant text and a function call (Gemini commonly does this), the
        text is emitted as a standalone ``assistant`` row *before* the
        ``tool_use`` row. This mirrors the live SSE path, where text and tool
        calls are streamed as separate messages — otherwise turn_grouper would
        render the tool_use by name/input only and silently drop the text.
        """
        # ADK stores per-invocation runtime objects (SkillCallContext, ProjectManager,
        # ToolSandbox, ...) in actions.state_delta. Those objects are only needed while
        # the current Runner invocation is alive and cannot be serialized into DB.
        raw_dump = event.model_dump(
            mode="json",
            exclude_none=True,
            exclude={"actions": {"state_delta"}},
        )

        content = []
        if event.content and event.content.parts:
            for part in event.content.parts:
                if getattr(part, "text", None):
                    content.append({"type": "text", "text": part.text})

        function_calls = event.get_function_calls()
        if event.author == "user":
            primary_type = "user"
        elif function_calls:
            primary_type = "tool_use"
        elif event.get_function_responses():
            primary_type = "tool_result"
        elif event.content and any(
            getattr(part, "thought", None) or getattr(part, "thought_signature", None)
            for part in event.content.parts
            if part
        ):
            primary_type = "thinking"
        else:
            primary_type = "assistant"

        timestamp = event.created_at.isoformat() if hasattr(event, "created_at") and event.created_at else None

        rows: list[dict[str, Any]] = []

        # Split off assistant text that rides along with a tool call so it stays
        # renderable. The standalone row deliberately omits ``adk_event`` — ADK
        # replay reconstructs the full event from the tool_use row's dump, so
        # carrying the text here too would duplicate it on replay.
        if primary_type == "tool_use" and content:
            rows.append({"type": "assistant", "content": content, "timestamp": timestamp, "_adk_replay_skip": True})
            content = []

        result = {
            "type": primary_type,
            "content": content,
            "adk_event": raw_dump,
            "timestamp": timestamp,
        }

        # Populate tool specific legacy fields
        if primary_type == "tool_use" and function_calls:
            call = function_calls[0]
            result.update({"name": call.name, "input": call.args, "tool_use_id": call.id})
        elif primary_type == "tool_result":
            responses = event.get_function_responses()
            if responses:
                res = responses[0]
                result.update({"tool_use_id": res.id, "content": res.response})

        rows.append(result)
        return rows

    def _dict_to_event(self, d: dict[str, Any]) -> Event:
        if "adk_event" in d:
            return Event.model_validate(d["adk_event"])

        # Legacy fallback
        msg_type = d.get("type")
        content_parts = []
        author = "user"

        # Handle content
        legacy_content = d.get("content")
        if isinstance(legacy_content, list):
            for block in legacy_content:
                if block.get("type") == "text":
                    content_parts.append({"text": block.get("text", "")})
        elif isinstance(legacy_content, str):
            content_parts.append({"text": legacy_content})

        if msg_type == "assistant":
            author = "model"
        elif msg_type == "tool_use":
            author = "model"
            content_parts.append(
                {
                    "function_call": {
                        "name": d.get("name", ""),
                        "args": d.get("input", {}),
                        "id": d.get("tool_use_id", ""),
                    }
                }
            )
        elif msg_type == "tool_result":
            author = "user"
            content_parts.append(
                {
                    "function_response": {
                        "name": d.get("name", ""),  # legacy might not have name here
                        "response": d.get("content", {}),
                        "id": d.get("tool_use_id", ""),
                    }
                }
            )

        if not content_parts:
            # Fallback to serializing the whole dict if no content found
            import json

            content_parts.append({"text": json.dumps(d)})

        return Event(author=author, content={"parts": content_parts})
