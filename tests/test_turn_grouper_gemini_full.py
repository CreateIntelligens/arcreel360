"""``turn_grouper`` 对 gemini-full 独立 ``tool_use`` / ``tool_result`` message 的处理。

gemini-full provider 与 Claude SDK 不同：每個 functionCall / functionResponse 是一条
独立的 top-level message（``type=tool_use`` / ``type=tool_result``），而不是嵌入在
assistant message 的 content blocks 里。本测试覆盖 turn_grouper 把它们正确合并到
assistant turn 的行为。
"""

from __future__ import annotations

from server.agent_runtime.turn_grouper import group_messages_into_turns


def test_tool_use_attaches_to_preceding_assistant() -> None:
    """assistant text 在前 → tool_use 应附在同一 assistant turn 内。"""
    raw = [
        {"type": "user", "content": "查项目状态", "uuid": "u1"},
        {
            "type": "assistant",
            "content": [{"type": "text", "text": "好的，让我检查"}],
            "uuid": "a1",
        },
        {
            "type": "tool_use",
            "tool_use_id": "tu-1",
            "name": "manga_workflow_status",
            "input": {},
            "uuid": "tu1",
        },
        {
            "type": "tool_result",
            "tool_use_id": "tu-1",
            "content": {"stage": 1},
            "is_error": False,
            "uuid": "tr1",
        },
        {
            "type": "assistant",
            "content": [{"type": "text", "text": "目前阶段 1"}],
            "uuid": "a2",
        },
        {"type": "result", "subtype": "success", "is_error": False},
    ]

    turns = group_messages_into_turns(raw)
    # user turn + assistant turn
    assert len(turns) == 2
    assert turns[0]["type"] == "user"
    assert turns[1]["type"] == "assistant"

    blocks = turns[1]["content"]
    types = [b.get("type") for b in blocks]
    # 应包含 text + tool_use + 第二段 text；tool_use 的 result 已写回同 block
    assert "tool_use" in types
    tool_use_block = next(b for b in blocks if b.get("type") == "tool_use")
    assert tool_use_block["id"] == "tu-1"
    assert tool_use_block["name"] == "manga_workflow_status"
    # turn_schema.normalize_block 會把 dict result 序列化為 JSON 字串(避免前端
    # 把物件直接當 React child 渲染、觸發 React error #31)。tool_result.content
    # 在進入 turn_grouper 時若是 dict,出口會變成字串。
    assert tool_use_block.get("result") == '{"stage": 1}'
    assert tool_use_block.get("is_error") is False


def test_split_assistant_text_before_tool_use_renders_text() -> None:
    """一個同時帶 text 與 functionCall 的 ADK event，被持久化拆成
    ``assistant`` text row + ``tool_use`` row（見 adk_session_service
    ``_event_to_dicts``）。turn_grouper 應把兩者併入同一 assistant turn，
    使 assistant 文字在重載歷史時不會遺失。回歸：先前 text 被吞進 tool_use。"""
    raw = [
        {"type": "user", "content": "讀一下 project.json", "uuid": "u1"},
        {
            "type": "assistant",
            "content": [{"type": "text", "text": "好的，我先讀取專案檔案。"}],
            "_adk_replay_skip": True,
            "uuid": "a1",
        },
        {
            "type": "tool_use",
            "tool_use_id": "tu-1",
            "name": "fs_read",
            "input": {"path": "project.json"},
        },
    ]

    turns = group_messages_into_turns(raw)
    assert len(turns) == 2
    assert turns[1]["type"] == "assistant"
    blocks = turns[1]["content"]
    types = [b.get("type") for b in blocks]
    assert types == ["text", "tool_use"]
    assert blocks[0]["text"] == "好的，我先讀取專案檔案。"
    assert blocks[1]["name"] == "fs_read"


def test_tool_use_without_preceding_assistant_starts_new_turn() -> None:
    """tool_use 是第一条消息时（罕见），创建新 assistant turn。"""
    raw = [
        {"type": "user", "content": "执行", "uuid": "u1"},
        {
            "type": "tool_use",
            "tool_use_id": "tu-x",
            "name": "fs_read",
            "input": {"path": "scripts/x.json"},
        },
        {
            "type": "tool_result",
            "tool_use_id": "tu-x",
            "content": {"content": "{}"},
            "is_error": False,
        },
    ]
    turns = group_messages_into_turns(raw)
    assert len(turns) == 2
    assert turns[1]["type"] == "assistant"
    blocks = turns[1]["content"]
    assert blocks[0]["type"] == "tool_use"
    assert blocks[0]["id"] == "tu-x"
    assert blocks[0]["result"] == '{"content": "{}"}'


def test_orphan_tool_result_is_dropped() -> None:
    """没有 tool_use 配对的孤儿 tool_result 应被静默忽略，不破坏 user turn。"""
    raw = [
        {"type": "user", "content": "hi"},
        {
            "type": "tool_result",
            "tool_use_id": "missing",
            "content": "x",
            "is_error": False,
        },
    ]
    turns = group_messages_into_turns(raw)
    # 仅保留 user turn（没有 assistant 在前，孤儿 result 被丢弃）
    assert len(turns) == 1
    assert turns[0]["type"] == "user"


def test_multiple_tool_uses_in_one_round() -> None:
    """模型一轮吐两個 functionCall：都应附在同一 assistant turn。"""
    raw = [
        {"type": "user", "content": "go"},
        {"type": "assistant", "content": [{"type": "text", "text": "处理中"}]},
        {"type": "tool_use", "tool_use_id": "a", "name": "fs_list", "input": {"path": "scripts"}},
        {"type": "tool_use", "tool_use_id": "b", "name": "fs_read", "input": {"path": "project.json"}},
        {"type": "tool_result", "tool_use_id": "a", "content": {"entries": []}, "is_error": False},
        {"type": "tool_result", "tool_use_id": "b", "content": {"content": "{}"}, "is_error": False},
        {"type": "assistant", "content": [{"type": "text", "text": "好"}]},
        {"type": "result", "subtype": "success", "is_error": False},
    ]
    turns = group_messages_into_turns(raw)
    assistant_turn = next(t for t in turns if t["type"] == "assistant")
    tool_uses = [b for b in assistant_turn["content"] if b.get("type") == "tool_use"]
    assert len(tool_uses) == 2
    ids = {b["id"] for b in tool_uses}
    assert ids == {"a", "b"}
    # 两個 result 都应回写到对应 tool_use
    by_id = {b["id"]: b for b in tool_uses}
    assert by_id["a"]["result"] == '{"entries": []}'
    assert by_id["b"]["result"] == '{"content": "{}"}'
