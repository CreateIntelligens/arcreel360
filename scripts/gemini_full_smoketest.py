"""真实 Gemini API 联调脚本（task 6.2 / 6.3）。

用法：
    uv run python -m scripts.gemini_full_smoketest --mock

行为：
1. 创建临时 demo 项目（如不存在）
2. 用 GeminiFullRuntimeProvider 跑一個对话，让模型必须调用 manga_workflow_status 工具
3. 验证返回了 stage 信息
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock

from google.genai.types import Content, FunctionCall, FunctionResponse, Part

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger("gemini-full-smoketest")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="Run with mock Gemini client")
    args_cmd = parser.parse_args()

    from lib.project_manager import ProjectManager
    from server.agent_runtime.adk_gemini_full_runtime_provider import (
        AdkGeminiFullRuntimeProvider as GeminiFullRuntimeProvider,
    )
    from server.agent_runtime.session_store import SessionMetaStore

    project_root = Path(".").absolute()
    pm = ProjectManager(projects_root=str(project_root / "projects"))

    project_name = "smoketest-gemini-full"
    project_dir = project_root / "projects" / project_name
    if not project_dir.exists():
        log.info("creating temp project %s", project_name)
        pm.create_project(project_name)
        # 走與 WebUI 相同的建立路徑，確保 project.json 必填欄位齊全
        pm.create_project_metadata(
            project_name,
            title="smoketest",
            style="anime",
            content_mode="narration",
        )

    provider = GeminiFullRuntimeProvider(
        project_root=project_root,
        data_dir=project_root / "projects" / ".agent_data",
        meta_store=SessionMetaStore(),
        max_tool_turns=8,
    )

    if args_cmd.mock:
        log.info("Running in MOCK mode")
        mock_client = MagicMock()
        mock_runner = MagicMock()
        from google.adk.events.event import Event

        async def fake_adk_run(*a, **k):
            # Simulate a tool call then a response
            yield Event(
                author="model",
                content=Content(
                    parts=[Part(function_call=FunctionCall(name="manga_workflow_status", args={}, id="call-1"))]
                ),
            )
            yield Event(
                author="user",
                content=Content(
                    parts=[
                        Part(
                            function_response=FunctionResponse(
                                name="manga_workflow_status", response={"stage": "script"}, id="call-1"
                            )
                        )
                    ]
                ),
            )
            yield Event(author="model", content=Content(parts=[Part(text="Everything looks good.")]))

        mock_runner.run_async = fake_adk_run
        monkeypatch_provider(provider, mock_client, mock_runner)

    # ---- 测试 1：让模型用 manga_workflow_status 报告项目阶段
    log.info("=" * 60)
    log.info("test 1: workflow status query")
    log.info("=" * 60)
    sid = await provider.send_new_session(
        project_name,
        "请用 manga_workflow_status 工具检查当前项目处于哪個阶段，然后告诉我下一步该做什么。",
        echo_text="请检查项目状态",
    )
    managed = provider._sessions[sid]
    try:
        await asyncio.wait_for(managed.generation_task, timeout=120)  # type: ignore[arg-type]
    except TimeoutError:
        log.error("turn timed out after 120s")
        return 1

    tool_uses = [m for m in managed.message_buffer if m.get("type") == "tool_use"]
    tool_results = [m for m in managed.message_buffer if m.get("type") == "tool_result"]
    assistants = [m for m in managed.message_buffer if m.get("type") == "assistant"]

    log.info("tool_use count: %d", len(tool_uses))
    for tu in tool_uses:
        log.info("  → %s(%s)", tu.get("name"), tu.get("input"))
    log.info("tool_result count: %d", len(tool_results))
    for tr in tool_results:
        content = tr.get("content")
        log.info("  ← %s", str(content)[:200])
    log.info("assistant text:")
    for a in assistants:
        for block in a.get("content", []):
            if block.get("type") == "text":
                log.info("  %s", block["text"][:300])

    if not tool_uses:
        log.error("FAIL: model did not call any tool")
        return 2
    if managed.status != "completed":
        log.error("FAIL: session ended with status=%s", managed.status)
        return 3

    log.info("=" * 60)
    log.info("smoketest finished OK")
    log.info("=" * 60)
    return 0


def monkeypatch_provider(provider, client, runner):
    async def fake_get_client():
        return client, "fake-model"

    provider._get_genai_client = fake_get_client

    import server.agent_runtime.adk_gemini_full_runtime_provider

    server.agent_runtime.adk_gemini_full_runtime_provider.Runner = lambda **k: runner


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
