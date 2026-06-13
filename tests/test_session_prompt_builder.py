from pathlib import Path

from server.agent_runtime.session_prompt_builder import append_overview_section, build_project_context


def test_append_overview_section_noop_on_none():
    parts: list[str] = []
    append_overview_section(parts, None)
    assert parts == []


def test_build_project_context_includes_name():
    ctx = build_project_context(
        project_name="demo",
        project={"title": "T"},
        project_cwd=Path("/tmp/projects/demo"),
        overview=None,
    )
    assert "demo" in ctx
