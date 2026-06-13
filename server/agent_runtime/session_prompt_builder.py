"""
Pure prompt builders for Claude SDK sessions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lib import agent_profile


def append_overview_section(parts: list[str], overview: Any) -> None:
    """Append project overview fields to prompt parts."""
    if not isinstance(overview, dict) or not overview:
        return
    parts.append("")
    parts.append("### 專案概述")
    if synopsis := overview.get("synopsis"):
        parts.append(synopsis)
    if genre := overview.get("genre"):
        parts.append(f"- 題材：{genre}")
    if theme := overview.get("theme"):
        parts.append(f"- 主題：{theme}")
    if world := overview.get("world_setting"):
        parts.append(f"- 世界觀：{world}")


def build_project_context(
    *,
    project_name: str,
    project: dict[str, Any],
    project_cwd: Path,
    overview: Any = None,
    relative_skills_prefix: str = agent_profile.RELATIVE_SKILLS_PREFIX,
) -> str:
    """Build project-specific context from project metadata."""
    parts = [
        "## 目前專案上下文",
        "",
        f"- 專案識別：{project_name}",
    ]

    if title := project.get("title"):
        parts.append(f"- 專案標題：{title}")
    if mode := project.get("content_mode"):
        parts.append(f"- 內容模式：{mode}")
    if style := project.get("style"):
        parts.append(f"- 視覺風格：{style}")
    if style_desc := project.get("style_description"):
        parts.append(f"- 風格描述：{style_desc}")
    parts.append(f"- 專案目錄（即目前工作目錄 cwd）：{project_cwd}")
    parts.append(
        "- Read/Edit/Write 等工具的 file_path 引數必須使用絕對路徑，不要使用相對路徑，也不要把專案標題當成目錄名。"
    )
    parts.append(
        f"- Bash 呼叫 skill 指令碼時必須使用相對路徑（如 `python {relative_skills_prefix}/.../script.py`），不要轉成絕對路徑。"
    )
    parts.append("- Bash 命令必須寫在單行，禁止使用 `\\` 換行，JSON 引數請使用緊湊格式。")

    append_overview_section(parts, project.get("overview", overview))
    return "\n".join(parts)


def build_append_prompt(
    persona_prompt: str,
    *,
    project_name: str,
    project: dict[str, Any] | None,
    project_cwd: Path | None,
) -> str:
    """Combine the persona prompt and optional project context."""
    parts = [persona_prompt]
    if project is not None and project_cwd is not None:
        parts.append(
            build_project_context(
                project_name=project_name,
                project=project,
                project_cwd=project_cwd,
            )
        )
    return "\n".join(parts)
