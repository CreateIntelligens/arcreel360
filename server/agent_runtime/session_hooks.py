"""
Claude SDK Client sessions hooks.
Contains file access control and JSON validation/backup/restore hooks.
"""

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from lib import agent_profile

logger = logging.getLogger(__name__)

DEFAULT_WRITE_TOOLS = {"Write", "Edit"}
DEFAULT_WRITABLE_EXTENSIONS = {".json", ".md", ".txt"}
CLAUDE_PROJECTS_DIR: Path = Path.home() / ".claude" / "projects"
CURLY_QUOTES = "\u201c\u201d\u201e\u201f"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _has_curly_quotes(text: str) -> bool:
    """Return True if *text* contains Unicode curly/smart quotes."""
    return any(ch in CURLY_QUOTES for ch in text)


def _resolve_tool_path(project_cwd: Path, file_path: str) -> Path:
    path = Path(file_path)
    return (project_cwd / path).resolve() if not path.is_absolute() else path.resolve()


def encode_sdk_project_path(project_cwd: Path) -> str:
    """Encode a project cwd the same way the SDK does for session storage."""
    return project_cwd.as_posix().replace("/", "-").replace(".", "-")


def is_path_allowed(
    file_path: str,
    tool_name: str = "Read",
    project_cwd: Path | None = None,
    *,
    project_root: Path,
    write_tools: set[str] = DEFAULT_WRITE_TOOLS,
    writable_extensions: set[str] = DEFAULT_WRITABLE_EXTENSIONS,
    sdk_projects_dir: Path = CLAUDE_PROJECTS_DIR,
) -> tuple[bool, str | None]:
    """Check if file_path is allowed for the given tool."""
    project_root = Path(project_root).resolve()
    project_cwd = Path(project_cwd or project_root).resolve()
    try:
        resolved = _resolve_tool_path(project_cwd, file_path)
    except (ValueError, OSError):
        return False, "存取遭拒：無效的檔案路徑"

    if resolved.is_relative_to(project_cwd):
        if tool_name in write_tools:
            ext = resolved.suffix.lower()
            if ext not in writable_extensions:
                return False, (
                    f"不允許建立／編輯 {ext} 型別的檔案。"
                    "Write/Edit 僅限 .json、.md、.txt 檔案。"
                    "如果你需要執行資料處理，請使用既有的 skill 指令碼。"
                )
        return True, None

    if tool_name in write_tools:
        return False, "存取遭拒：不允許存取目前專案目錄之外的路徑"

    if resolved.is_relative_to(project_root):
        return True, None

    encoded = encode_sdk_project_path(project_cwd)
    sdk_project_dir = sdk_projects_dir / encoded
    if resolved.is_relative_to(sdk_project_dir) and "tool-results" in resolved.parts:
        return True, None

    sdk_tmp_prefixes = ("/tmp/claude-", "/private/tmp/claude-")
    resolved_str = str(resolved)
    if resolved_str.startswith(sdk_tmp_prefixes) and "tasks" in resolved.parts:
        return True, None

    return False, "存取遭拒：不允許存取目前專案與公共目錄之外的路徑"


async def handle_ask_user_question(
    managed: Any,
    tool_name: str,
    input_data: dict[str, Any],
    *,
    permission_allow_cls: Any,
    permission_deny_cls: Any,
) -> Any:
    """Handle AskUserQuestion tool invocation within can_use_tool callback."""
    if managed is None:
        return permission_allow_cls(updated_input=input_data)

    raw_questions = input_data.get("questions")
    questions = raw_questions if isinstance(raw_questions, list) else []
    payload = {
        "type": "ask_user_question",
        "question_id": f"aq_{uuid4().hex}",
        "tool_name": tool_name,
        "questions": questions,
        "timestamp": _utc_now_iso(),
    }
    pending = managed.add_pending_question(payload)
    managed.add_message(payload)

    try:
        answers = await pending.answer_future
    except Exception as exc:
        if permission_deny_cls is not None:
            return permission_deny_cls(
                message=str(exc) or "會話已被使用者中斷",
                interrupt=True,
            )
        raise
    merged_input = dict(input_data or {})
    merged_input["answers"] = answers
    return permission_allow_cls(updated_input=merged_input)


def build_can_use_tool_callback(
    *,
    session_id: str,
    sessions: dict[str, Any],
    handle_ask_user_question_fn: Callable[[Any, str, dict[str, Any]], Any],
    permission_allow_cls: Any,
    permission_deny_cls: Any,
    relative_skills_prefix: str = agent_profile.RELATIVE_SKILLS_PREFIX,
    managed_ref: list[Any] | None = None,
) -> Callable[[str, dict[str, Any], Any], Any]:
    """Create per-session can_use_tool callback (default-deny)."""

    async def _can_use_tool(
        tool_name: str,
        input_data: dict[str, Any],
        _context: Any,
    ) -> Any:
        if permission_allow_cls is None:
            raise RuntimeError("claude_agent_sdk is not installed")

        normalized_tool = str(tool_name or "").strip().lower()

        if normalized_tool == "askuserquestion":
            managed = managed_ref[0] if managed_ref else sessions.get(session_id)
            return await handle_ask_user_question_fn(
                managed,
                tool_name,
                input_data,
            )

        if permission_deny_cls is not None:
            hint = (
                f"未授權的工具呼叫：{tool_name}"
                f"({json.dumps(input_data, ensure_ascii=False)[:200]})\n"
                "目前 Bash 白名單僅允許以下命令：\n"
                f"  - python {relative_skills_prefix}/<skill>/scripts/<script>.py <args>（必須使用相對路徑）\n"
                "  - ffmpeg / ffprobe\n"
                "其他 Bash 命令都不可用。"
                "請檢查命令格式是否符合白名單規則。"
            )
            return permission_deny_cls(message=hint)
        return permission_allow_cls(updated_input=input_data)

    return _can_use_tool


def build_file_access_hook(
    project_cwd: Path,
    path_tools: dict[str, str],
    is_path_allowed_fn: Callable[[str, str, Path], tuple[bool, str | None]],
) -> Callable[..., Any]:
    """Build a PreToolUse hook callback that enforces file access control.

    PreToolUse hooks are step 1 in the SDK permission chain and fire for
    **every** tool call, including Read/Glob/Grep which would otherwise
    be auto-approved by allow rules at step 4.
    """

    async def _file_access_hook(
        input_data: dict[str, Any],
        _tool_use_id: str | None,
        _context: Any,
    ) -> dict[str, Any]:
        tool_name = input_data.get("tool_name", "")
        if tool_name not in path_tools:
            return {"continue_": True}

        tool_input = input_data.get("tool_input", {})
        path_key = path_tools[tool_name]
        file_path = tool_input.get(path_key)

        if file_path:
            allowed, deny_reason = is_path_allowed_fn(
                file_path,
                tool_name,
                project_cwd,
            )
            if not allowed:
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": deny_reason,
                    },
                }

        return {"continue_": True}

    return _file_access_hook


def build_json_validation_hook(
    project_cwd: Path,
    json_backups: dict[str, tuple[Path, str]] | None = None,
) -> Callable[..., Any]:
    """Build a PreToolUse hook that blocks Write/Edit when the result would
    produce invalid JSON.

    For Edit: reads the current file, simulates the string replacement, and
    validates the result with ``json.loads()``.
    For Write: validates the ``content`` parameter directly.

    When *json_backups* is provided, the hook saves the current file
    content before the edit so the PostToolUse hook can restore it if
    the actual result turns out to be invalid.

    Returns ``permissionDecision: "deny"`` to block the operation before it
    executes, giving the agent a chance to fix its input and retry.
    """

    async def _json_validation_hook(
        input_data: dict[str, Any],
        _tool_use_id: str | None,
        _context: Any,
    ) -> dict[str, Any]:
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})

        file_path = tool_input.get("file_path", "")
        if not file_path or not file_path.endswith(".json"):
            return {}

        # --- Simulate the result without touching the file ---
        simulated: str | None = None

        if tool_name == "Write":
            simulated = tool_input.get("content")
            logger.info(
                "JSON 校驗 hook: tool=Write file=%s content_len=%s",
                file_path,
                len(simulated) if simulated else 0,
            )
        elif tool_name == "Edit":
            old_string = tool_input.get("old_string", "")
            new_string = tool_input.get("new_string", "")
            if not old_string:
                logger.info(
                    "JSON 校驗 hook: tool=Edit file=%s skip=old_string為空",
                    file_path,
                )
                return {}

            # Detect curly quotes early — Claude Code may normalise
            # old_string internally (allowing the edit to succeed) while
            # the hook's exact-match ``old_string not in current`` check
            # below would skip validation, letting curly quotes slip into
            # the file and corrupt JSON.
            if _has_curly_quotes(new_string):
                curly_found = [f"U+{ord(ch):04X}" for ch in new_string if ch in CURLY_QUOTES]
                logger.warning(
                    "PreToolUse JSON 校驗攔截(彎引號): file=%s curly=%s",
                    file_path,
                    curly_found[:5],
                )
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": (
                            "操作被阻止：new_string 包含彎引號"
                            "（\u201c 或 \u201d），"
                            "這會破壞 JSON 格式。"
                            "請將所有彎引號替換為標準 ASCII "
                            "雙引號 (U+0022) 後重試。"
                        ),
                    },
                }

            resolved = _resolve_tool_path(project_cwd, file_path)
            try:
                current = resolved.read_text(encoding="utf-8")
            except OSError as read_err:
                logger.info(
                    "JSON 校驗 hook: tool=Edit file=%s skip=讀取失敗 error=%s",
                    file_path,
                    read_err,
                )
                return {}

            # Save backup for PostToolUse restore on corruption
            if json_backups is not None and _tool_use_id:
                json_backups[_tool_use_id] = (resolved, current)

            if old_string not in current:
                # Edit tool will fail on its own; no need to intervene.
                logger.info(
                    "JSON 校驗 hook: tool=Edit file=%s skip=old_string未匹配 old_len=%d new_len=%d file_len=%d",
                    file_path,
                    len(old_string),
                    len(new_string),
                    len(current),
                )
                return {}

            replace_all = tool_input.get("replace_all", False)
            if replace_all:
                simulated = current.replace(old_string, new_string)
            else:
                simulated = current.replace(old_string, new_string, 1)

            logger.info(
                "JSON 校驗 hook: tool=Edit file=%s matched=True old_len=%d new_len=%d simulated_len=%d replace_all=%s",
                file_path,
                len(old_string),
                len(new_string),
                len(simulated),
                replace_all,
            )

        if simulated is None:
            return {}

        try:
            json.loads(simulated)
            logger.info(
                "JSON 校驗 hook: tool=%s file=%s result=valid",
                tool_name,
                file_path,
            )
            return {}
        except json.JSONDecodeError as exc:
            logger.warning(
                "PreToolUse JSON 校驗攔截: file=%s tool=%s error=%s",
                file_path,
                tool_name,
                exc,
            )
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"操作已被阻止：此次 {tool_name} 會讓 {file_path} "
                        f"變成無效 JSON。錯誤：{exc}。"
                        "請檢查你的輸入內容是否包含未跳脫的雙引號或其他"
                        "JSON 語法問題，修正後再試。"
                    ),
                },
            }

    return _json_validation_hook


def build_json_post_validation_hook(
    project_cwd: Path,
    json_backups: dict[str, tuple[Path, str]],
) -> Callable[..., Any]:
    """Build a PostToolUse hook that validates JSON files after Write/Edit.

    This is a safety net for cases where the PreToolUse simulation fails
    to catch invalid edits (e.g. due to old_string mismatch or escaping
    differences between the hook simulation and the actual Edit tool).

    If the file is invalid JSON after the edit, the hook:
    1. Restores the file from the backup saved by the PreToolUse hook
    2. Returns ``additionalContext`` telling the agent what went wrong
    """

    async def _json_post_validation_hook(
        input_data: dict[str, Any],
        tool_use_id: str | None,
        _context: Any,
    ) -> dict[str, Any]:
        # Top-level guard: unhandled exceptions in hooks interrupt the
        # agent (per SDK docs), so we catch everything and log.
        try:
            return await _json_post_validation_impl(
                input_data,
                tool_use_id,
            )
        except Exception:
            logger.exception("PostToolUse JSON 校驗 hook 異常")
            return {}

    async def _json_post_validation_impl(
        input_data: dict[str, Any],
        tool_use_id: str | None,
    ) -> dict[str, Any]:
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})

        file_path = tool_input.get("file_path", "")
        if not file_path or not file_path.endswith(".json"):
            return {}

        # Pop the backup regardless of outcome to avoid memory leaks
        backup = json_backups.pop(tool_use_id, None) if tool_use_id else None

        resolved = _resolve_tool_path(project_cwd, file_path)

        try:
            actual = resolved.read_text(encoding="utf-8")
        except OSError:
            return {}

        try:
            json.loads(actual)
            logger.info(
                "PostToolUse JSON 校驗: tool=%s file=%s result=valid",
                tool_name,
                file_path,
            )
            return {}
        except json.JSONDecodeError as exc:
            # File is corrupt — restore from backup if available
            restored = False
            if backup:
                backup_path, backup_content = backup
                try:
                    backup_path.write_text(backup_content, encoding="utf-8")
                    restored = True
                    logger.warning(
                        "PostToolUse JSON 校驗攔截並恢復: file=%s tool=%s error=%s backup_restored=True",
                        file_path,
                        tool_name,
                        exc,
                    )
                except OSError as write_err:
                    logger.error(
                        "PostToolUse JSON 備份恢復失敗: file=%s error=%s",
                        file_path,
                        write_err,
                    )
            else:
                logger.warning(
                    "PostToolUse JSON 校驗攔截(無備份): file=%s tool=%s error=%s",
                    file_path,
                    tool_name,
                    exc,
                )

            if restored:
                ctx = (
                    f"⚠ 已偵測到 JSON 損壞並完成回滾：{tool_name} 導致 "
                    f"{file_path} 變成無效 JSON（{exc}）。"
                    "檔案已恢復到編輯前狀態，請修正後再試。"
                )
            else:
                ctx = (
                    f"⚠ 已偵測到 JSON 損壞但無法恢復：{tool_name} 導致 "
                    f"{file_path} 變成無效 JSON（{exc}）。"
                    "檔案目前仍為損壞狀態（沒有可用備份或恢復寫入失敗），"
                    "請先讀取檔案確認內容，再手動修正為合法 JSON。"
                )

            return {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": ctx,
                },
            }

    return _json_post_validation_hook
