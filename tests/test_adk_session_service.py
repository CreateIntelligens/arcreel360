import pytest
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from lib.db.base import Base
from lib.db.repositories.agent_message_repo import AgentMessageRepository
from lib.project_manager import ProjectManager
from server.agent_runtime.adk_session_service import AgentMessagesSessionService
from server.agent_runtime.skill_function_declarations import SkillCallContext
from server.agent_runtime.tool_sandbox import ToolSandbox


@pytest.fixture
async def session_service():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = AgentMessagesSessionService("test_project", session_factory=factory)
    yield service
    await engine.dispose()


@pytest.mark.asyncio
async def test_session_creation(session_service):
    session = await session_service.create_session(app_name="test_app", user_id="test_user")
    assert session.id.startswith("gemini-full:")


@pytest.mark.asyncio
async def test_append_and_list_event(session_service):
    session = await session_service.create_session(app_name="test_app", user_id="test_user")

    event = Event(author="user", content={"parts": [{"text": "hello"}]})
    await session_service.append_event(session, event)

    events = await session_service.list_events(session.id)
    assert len(events) == 1
    assert events[0].id == event.id
    assert events[0].content.parts[0].text == "hello"


@pytest.mark.asyncio
async def test_append_event_omits_non_serializable_skill_context(session_service, tmp_path):
    project_root = tmp_path / "projects"
    project_name = "demo"
    (project_root / project_name).mkdir(parents=True)
    skill_ctx = SkillCallContext(
        project_name=project_name,
        sandbox=ToolSandbox(project_root=project_root, project_name=project_name),
        project_manager=ProjectManager(projects_root=str(project_root)),
        session_id="gemini-full:test",
    )
    session = await session_service.create_session(app_name="test_app", user_id="test_user")
    event = Event(
        author="user",
        content={"parts": [{"text": "hello"}]},
        actions=EventActions(state_delta={"skill_ctx": skill_ctx}),
    )

    await session_service.append_event(session, event)

    async with session_service._session_factory() as db_session:
        stored = await AgentMessageRepository(db_session).list(session.id)
    assert stored[0]["adk_event"]["content"]["parts"][0]["text"] == "hello"
    assert "skill_ctx" not in stored[0]["adk_event"].get("actions", {}).get("state_delta", {})

    events = await session_service.list_events(session.id)
    assert events[0].content.parts[0].text == "hello"


@pytest.mark.asyncio
async def test_parallel_function_call(session_service):
    session = await session_service.create_session(app_name="test_app", user_id="test_user")

    event = Event(
        author="agent",
        content={
            "parts": [
                {"function_call": {"name": "tool1", "args": {"a": 1}}},
                {"function_call": {"name": "tool2", "args": {"b": 2}}},
            ]
        },
    )
    await session_service.append_event(session, event)

    events = await session_service.list_events(session.id)
    assert len(events) == 1
    fcalls = events[0].get_function_calls()
    assert len(fcalls) == 2
    assert fcalls[0].name == "tool1"
    assert fcalls[1].name == "tool2"


@pytest.mark.asyncio
async def test_event_with_text_and_function_call_persists_assistant_text(session_service):
    """An ADK event carrying both assistant text and a function call must
    persist the text as a separate renderable assistant message, not swallow
    it inside the tool_use message (which turn_grouper renders by name/input
    only). This keeps the history path aligned with the live SSE path."""
    session = await session_service.create_session(app_name="test_app", user_id="test_user")

    event = Event(
        author="agent",
        content={
            "parts": [
                {"text": "好的，我先讀取專案檔案。"},
                {"function_call": {"name": "fs_read", "args": {"path": "project.json"}}},
            ]
        },
    )
    await session_service.append_event(session, event)

    async with session_service._session_factory() as db_session:
        stored = await AgentMessageRepository(db_session).list(session.id)

    # Expect two persisted messages: assistant text first, then tool_use.
    assert [m["type"] for m in stored] == ["assistant", "tool_use"]
    assistant_msg = stored[0]
    assert assistant_msg["content"] == [{"type": "text", "text": "好的，我先讀取專案檔案。"}]
    # The standalone assistant message must not carry adk_event, otherwise ADK
    # replay would reconstruct the text twice (once here, once via the tool_use
    # event's adk_event dump).
    assert "adk_event" not in assistant_msg

    tool_msg = stored[1]
    assert tool_msg["name"] == "fs_read"
    assert tool_msg["input"] == {"path": "project.json"}

    # ADK replay must still collapse back to a single event (text + call).
    events = await session_service.list_events(session.id)
    assert len(events) == 1
    assert events[0].get_function_calls()[0].name == "fs_read"
    text_parts = [p.text for p in events[0].content.parts if getattr(p, "text", None)]
    assert text_parts == ["好的，我先讀取專案檔案。"]


@pytest.mark.asyncio
async def test_tool_error_event(session_service):
    session = await session_service.create_session(app_name="test_app", user_id="test_user")
    event = Event(
        author="user",
        content={"parts": [{"function_response": {"name": "tool1", "response": {"error": "permission_denied"}}}]},
    )
    await session_service.append_event(session, event)

    events = await session_service.list_events(session.id)
    assert len(events) == 1
    fresps = events[0].get_function_responses()
    assert len(fresps) == 1
    assert fresps[0].name == "tool1"
    assert fresps[0].response["error"] == "permission_denied"


@pytest.mark.asyncio
async def test_unknown_event_fallback(session_service):
    # Test _dict_to_event fallback
    event = session_service._dict_to_event({"type": "unknown_legacy_format", "something": "else"})
    assert event.author == "user"
    assert "unknown_legacy_format" in event.content.parts[0].text
