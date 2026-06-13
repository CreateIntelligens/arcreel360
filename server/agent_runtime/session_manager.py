"""
Manages ClaudeSDKClient instances with background execution and reconnection support.
"""

import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncIterable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

from server.agent_runtime import sdk_process_control as proc
from server.agent_runtime import session_hooks, session_prompt_builder
from server.agent_runtime.managed_session import (
    ManagedSession,
    SessionCapacityError,
)
from server.agent_runtime.message_utils import extract_plain_user_content
from server.agent_runtime.models import SessionMeta, SessionStatus
from server.agent_runtime.session_store import SessionMetaStore

try:
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
    from claude_agent_sdk.types import HookMatcher, PermissionResultAllow, SystemPromptPreset

    try:
        from claude_agent_sdk.types import PermissionResultDeny
    except ImportError:
        PermissionResultDeny = None
    try:
        from claude_agent_sdk import tag_session
    except ImportError:
        tag_session = None

    SDK_AVAILABLE = True
except ImportError:
    ClaudeSDKClient = None
    ClaudeAgentOptions = None
    HookMatcher = None
    PermissionResultAllow = None
    PermissionResultDeny = None
    tag_session = None
    SDK_AVAILABLE = False

try:
    from lib.config.service import ConfigService
    from lib.db import async_session_factory
except ImportError:
    async_session_factory = None  # type: ignore[assignment]
    ConfigService = None  # type: ignore[assignment]

from lib import agent_profile


def _utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class SessionManager:
    """Manages all active ClaudeSDKClient instances."""

    DEFAULT_ALLOWED_TOOLS = [
        "Skill",
        "Task",
        "Read",
        "Write",
        "Edit",
        "Grep",
        "Glob",
        "AskUserQuestion",
    ]
    DEFAULT_SETTING_SOURCES = ["project"]
    _INTERRUPT_TIMEOUT = 2.0
    _DISCONNECT_TIMEOUT = 8.0
    _TERMINATE_WAIT_TIMEOUT = 2.0
    _KILL_WAIT_TIMEOUT = 2.0
    _SDK_ID_TIMEOUT = 60.0

    # Bash is NOT in DEFAULT_ALLOWED_TOOLS — it is controlled by declarative
    # allow rules in settings.json (whitelist approach, default deny).
    # File access control for Read/Write/Edit/Glob/Grep uses PreToolUse hooks.
    _PATH_TOOLS: dict[str, str] = {
        "Read": "file_path",
        "Write": "file_path",
        "Edit": "file_path",
        "Glob": "path",
        "Grep": "path",
    }
    _WRITE_TOOLS = {"Write", "Edit"}
    _WRITABLE_EXTENSIONS = {".json", ".md", ".txt"}

    # Sentinel used in pending_user_echoes for image-only messages (no text).
    # The SDK parser drops image blocks, so the replayed UserMessage arrives
    # with empty content; this sentinel lets _is_duplicate_user_echo match it.
    _IMAGE_ONLY_SENTINEL = "__image_only__"

    # SDK message class name to type mapping
    _MESSAGE_TYPE_MAP = {
        "UserMessage": "user",
        "AssistantMessage": "assistant",
        "ResultMessage": "result",
        "SystemMessage": "system",
        "StreamEvent": "stream_event",
        "TaskStartedMessage": "system",
        "TaskProgressMessage": "system",
        "TaskNotificationMessage": "system",
    }

    # Typed task message subtypes for precise classification
    _TASK_MESSAGE_SUBTYPES = {
        "TaskStartedMessage": "task_started",
        "TaskProgressMessage": "task_progress",
        "TaskNotificationMessage": "task_notification",
    }

    def __init__(
        self,
        project_root: Path,
        data_dir: Path,
        meta_store: SessionMetaStore,
    ):
        self.project_root = Path(project_root)
        self.data_dir = Path(data_dir)
        self.meta_store = meta_store
        self.sessions: dict[str, ManagedSession] = {}
        self._disconnecting: set[str] = set()
        self._connect_locks: dict[str, asyncio.Lock] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from environment (sync fallback)."""
        max_turns_env = os.environ.get("ASSISTANT_MAX_TURNS", "").strip()
        self.max_turns = int(max_turns_env) if max_turns_env else None

    async def refresh_config(self) -> None:
        """Reload configuration from ConfigService (DB), falling back to env."""
        try:
            from lib.config.service import ConfigService
            from lib.db import async_session_factory

            async with async_session_factory() as session:
                svc = ConfigService(session)
                raw = await svc.get_setting("assistant_max_turns", "")
                raw = raw.strip()
                if raw:
                    self.max_turns = int(raw)
                    return
        except Exception:
            logger.warning("從 DB 載入 assistant 配置失敗，回退到環境變數", exc_info=True)
        # Fallback to env var
        self._load_config()

    _PERSONA_PROMPT = """\
## 身份

你是 ArcReel AI Agent，一個專業的 AI 影片內容創作助理。你的職責是將小說轉化為可發布的短影片內容。

## 行為準則

- 所有面向使用者的回覆都必須使用繁體中文；除非使用者明確要求翻譯或輸出其他語言，否則不要使用簡體中文或英文作為主要回覆語言
- 主動引導使用者完成影片創作工作流，而不只是被動回答問題
- 遇到不確定的創作決策時，向使用者提出選項並給出建議，而不是自行決定
- 涉及多步驟任務時，使用 TodoWrite 追蹤進度並向使用者回報
- 你不能建立或編輯程式碼檔案（.py/.js/.sh 等），Write/Edit 僅限 .json/.md/.txt
- 你是使用者的影片製作搭檔，專業、友善、高效"""

    def _build_append_prompt(self, project_name: str) -> str:
        """Build the append portion for SystemPromptPreset."""
        loaded = self._load_project_context(project_name)
        if loaded is None:
            return session_prompt_builder.build_append_prompt(
                self._PERSONA_PROMPT,
                project_name=project_name,
                project=None,
                project_cwd=None,
            )
        project_cwd, project = loaded
        return session_prompt_builder.build_append_prompt(
            self._PERSONA_PROMPT,
            project_name=project_name,
            project=project,
            project_cwd=project_cwd,
        )

    def _load_project_context(self, project_name: str) -> tuple[Path, dict[str, Any]] | None:
        try:
            project_cwd = self._resolve_project_cwd(project_name)
        except (ValueError, FileNotFoundError):
            return None

        project_json = project_cwd / "project.json"
        if not project_json.exists():
            return None

        try:
            config = json.loads(project_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read project.json for %s: %s", project_name, exc)
            return None

        if not isinstance(config, dict):
            logger.warning("project.json for %s is not a JSON object", project_name)
            return None

        return project_cwd, config

    def _build_project_context(self, project_name: str) -> str:
        """Build project-specific context from project.json metadata."""
        loaded = self._load_project_context(project_name)
        if loaded is None:
            return ""
        project_cwd, project = loaded
        return session_prompt_builder.build_project_context(
            project_name=project_name,
            project=project,
            project_cwd=project_cwd,
        )

    @staticmethod
    def _append_overview_section(parts: list[str], overview: Any) -> None:
        session_prompt_builder.append_overview_section(parts, overview)

    def _build_options(
        self,
        project_name: str,
        resume_id: str | None = None,
        can_use_tool: Callable[[str, dict[str, Any], Any], Any] | None = None,
    ) -> Any:
        """Build ClaudeAgentOptions for a session."""
        if not SDK_AVAILABLE or ClaudeAgentOptions is None:
            raise RuntimeError("claude_agent_sdk is not installed")

        transcripts_dir = self.data_dir / "transcripts"
        transcripts_dir.mkdir(parents=True, exist_ok=True)
        project_cwd = self._resolve_project_cwd(project_name)

        # Build PreToolUse hooks — file access control MUST use hooks because
        # Read/Glob/Grep are matched by allow rules (step 4 in the SDK
        # permission chain) before reaching can_use_tool (step 5).  Hooks
        # (step 1) fire for ALL tool calls and can override allow rules.
        hooks = None
        if HookMatcher is not None:
            hook_callbacks: list[Any] = [
                session_hooks.build_file_access_hook(
                    project_cwd,
                    self._PATH_TOOLS,
                    self._is_path_allowed,
                ),
            ]
            if can_use_tool is not None:
                # Official Python SDK guidance: keep stream open when using
                # can_use_tool.
                hook_callbacks.insert(0, self._keep_stream_open_hook)

            # Shared dict: PreToolUse saves file backup, PostToolUse restores
            # on corruption.  Keyed by tool_use_id.
            json_backups: dict[str, tuple[Path, str]] = {}

            hooks = {
                "PreToolUse": [
                    HookMatcher(matcher=None, hooks=hook_callbacks),
                    HookMatcher(
                        matcher="Write|Edit",
                        hooks=[
                            session_hooks.build_json_validation_hook(project_cwd, json_backups),
                        ],
                    ),
                ],
                "PostToolUse": [
                    HookMatcher(
                        matcher="Write|Edit",
                        hooks=[
                            session_hooks.build_json_post_validation_hook(project_cwd, json_backups),
                        ],
                    ),
                ],
            }

        return ClaudeAgentOptions(
            cwd=str(project_cwd),
            setting_sources=self.DEFAULT_SETTING_SOURCES,
            allowed_tools=self.DEFAULT_ALLOWED_TOOLS,
            max_turns=self.max_turns,
            system_prompt=SystemPromptPreset(
                type="preset",
                preset="claude_code",
                append=self._build_append_prompt(project_name),
            ),
            include_partial_messages=True,
            resume=resume_id,
            can_use_tool=can_use_tool,
            hooks=hooks,
        )

    @staticmethod
    async def _keep_stream_open_hook(
        _input_data: dict[str, Any], _tool_use_id: str | None, _context: Any
    ) -> dict[str, bool]:
        """Required keep-alive hook for Python can_use_tool callback."""
        return {"continue_": True}

    def _resolve_project_cwd(self, project_name: str) -> Path:
        """Resolve and validate per-session project working directory."""
        projects_root = (self.project_root / "projects").resolve()
        project_cwd = (projects_root / project_name).resolve()
        try:
            project_cwd.relative_to(projects_root)
        except ValueError as exc:
            raise ValueError("invalid project name") from exc
        if not project_cwd.exists() or not project_cwd.is_dir():
            raise FileNotFoundError(f"project not found: {project_name}")
        return project_cwd

    async def send_new_session(
        self,
        project_name: str,
        prompt: str | AsyncIterable[dict],
        *,
        echo_text: str | None = None,
        echo_content: list[dict[str, Any]] | None = None,
    ) -> str:
        """Create a new session via send-first: connect SDK, send message, wait for sdk_session_id."""
        if not SDK_AVAILABLE or ClaudeSDKClient is None:
            raise RuntimeError("claude_agent_sdk is not installed")

        await self._ensure_capacity()
        temp_id = uuid4().hex
        managed_ref: list[ManagedSession | None] = [None]

        options = self._build_options(
            project_name,
            resume_id=None,
            can_use_tool=await self._build_can_use_tool_callback(temp_id, managed_ref),
        )
        client = ClaudeSDKClient(options=options)
        await client.connect()

        managed = ManagedSession(
            session_id=temp_id,
            client=client,
            status="running",
            project_name=project_name,
        )
        managed_ref[0] = managed
        managed.last_activity = time.monotonic()
        self.sessions[temp_id] = managed

        # Echo user message
        display_text = echo_text or (prompt if isinstance(prompt, str) else "")
        dedup_key = display_text or (self._IMAGE_ONLY_SENTINEL if echo_content else "")
        if dedup_key:
            managed.pending_user_echoes.append(dedup_key)
        managed.add_message(self._build_user_echo_message(display_text, echo_content))

        try:
            await managed.client.query(prompt)
        except Exception:
            logger.exception("新會話訊息傳送失敗")
            del self.sessions[temp_id]
            try:
                await client.disconnect()
            except Exception as disconnect_err:
                logger.warning("新會話斷開連線失敗: %s", disconnect_err)
            raise

        managed.consumer_task = asyncio.create_task(self._consume_messages(managed))

        # Wait for sdk_session_id with timeout; also monitor consumer task
        # so we fail fast if the background task crashes before the event fires.
        event_task = asyncio.create_task(managed.sdk_id_event.wait())
        try:
            await asyncio.wait(
                {event_task, managed.consumer_task},
                timeout=self._SDK_ID_TIMEOUT,
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            if not event_task.done():
                event_task.cancel()

        if not managed.sdk_id_event.is_set():
            if managed.consumer_task.done():
                logger.error("consumer_task 提前退出，未獲得 sdk_session_id temp_id=%s", temp_id)
            else:
                logger.error("等待 sdk_session_id 超時 temp_id=%s", temp_id)
            managed.cancel_pending_questions("session creation timed out")
            if managed.consumer_task and not managed.consumer_task.done():
                managed.consumer_task.cancel()
                await asyncio.gather(managed.consumer_task, return_exceptions=True)
            del self.sessions[temp_id]
            try:
                await client.disconnect()
            except Exception as disconnect_err:
                logger.warning("清理斷開連線失敗: %s", disconnect_err)
            raise TimeoutError("SDK 會話建立超時")

        sdk_id = managed.resolved_sdk_id
        assert sdk_id is not None
        # Key swap already done in _on_sdk_session_id_received
        assert managed.session_id == sdk_id

        return sdk_id

    async def get_or_connect(self, session_id: str, *, meta: Optional["SessionMeta"] = None) -> ManagedSession:
        """Get existing managed session or create new connection."""
        if session_id in self.sessions and session_id not in self._disconnecting:
            return self.sessions[session_id]

        # Per-session lock prevents concurrent connect() for the same session_id.
        if session_id not in self._connect_locks:
            self._connect_locks[session_id] = asyncio.Lock()
        lock = self._connect_locks[session_id]

        async with lock:
            # Re-check after acquiring lock
            if session_id in self.sessions:
                return self.sessions[session_id]

            if meta is None:
                meta = await self.meta_store.get(session_id)
                if meta is None:
                    raise FileNotFoundError(f"session not found: {session_id}")

            if not SDK_AVAILABLE or ClaudeSDKClient is None:
                raise RuntimeError("claude_agent_sdk is not installed")

            await self._ensure_capacity()
            options = self._build_options(
                meta.project_name,
                meta.id,  # SessionMeta.id 就是 sdk_session_id
                can_use_tool=await self._build_can_use_tool_callback(session_id),
            )
            client = ClaudeSDKClient(options=options)
            await client.connect()

            managed = ManagedSession(
                session_id=meta.id,  # 現在就是 sdk_session_id
                client=client,
                status=meta.status if meta.status != "idle" else "idle",
                project_name=meta.project_name,
                resolved_sdk_id=meta.id,  # 標記為已註冊，防止重複建立 DB 記錄
            )
            managed.sdk_id_event.set()  # 已有會話不需要等待
            self.sessions[session_id] = managed
            return managed

    async def send_message(
        self,
        session_id: str,
        prompt: str | AsyncIterable[dict],
        *,
        echo_text: str | None = None,
        echo_content: list[dict[str, Any]] | None = None,
        meta: Optional["SessionMeta"] = None,
    ) -> None:
        """Send a message and start background consumer."""
        managed = await self.get_or_connect(session_id, meta=meta)
        managed.last_activity = time.monotonic()
        # 取消待執行的 cleanup（會話恢復活躍）
        if managed._cleanup_task and not managed._cleanup_task.done():
            managed._cleanup_task.cancel()
            managed._cleanup_task = None

        if managed.status == "running":
            raise ValueError("會話正在處理中，請等待目前回覆完成後再傳送新訊息")

        self._prune_transient_buffer(managed)

        # Determine the display text for echo dedup (pending_user_echoes).
        # For image-only messages display_text is empty; use a sentinel so the
        # SDK-replayed empty-content user message can still be deduplicated.
        display_text = echo_text or (prompt if isinstance(prompt, str) else "")
        dedup_key = display_text or (self._IMAGE_ONLY_SENTINEL if echo_content else "")

        # Update in-memory status and echo user input immediately so live SSE
        # shows it even when SDK stream doesn't replay user messages in real time.
        managed.status = "running"
        if dedup_key:
            managed.pending_user_echoes.append(dedup_key)
            if len(managed.pending_user_echoes) > 20:
                managed.pending_user_echoes.pop(0)
        managed.add_message(self._build_user_echo_message(display_text, echo_content))

        # Persist status asynchronously — don't block the echo broadcast
        await self.meta_store.update_status(session_id, "running")

        # Send the query — restore status on failure so the session is not
        # permanently stuck in "running" without an active consumer.
        try:
            await managed.client.query(prompt)
        except Exception:
            logger.exception("會話訊息處理失敗")
            managed.pending_user_echoes.clear()
            managed.status = "error"
            await self.meta_store.update_status(session_id, "error")
            raise

        # Start consumer task if not running
        if managed.consumer_task is None or managed.consumer_task.done():
            managed.consumer_task = asyncio.create_task(self._consume_messages(managed))

    async def interrupt_session(self, session_id: str) -> SessionStatus:
        """Interrupt a running session."""
        meta = await self.meta_store.get(session_id)
        if meta is None:
            raise FileNotFoundError(f"session not found: {session_id}")

        managed = self.sessions.get(session_id)
        if managed is None:
            if meta.status == "running":
                await self.meta_store.update_status(session_id, "interrupted")
                return "interrupted"
            return meta.status

        if managed.status != "running":
            return managed.status

        managed.pending_user_echoes.clear()
        managed.interrupt_requested = True
        managed.cancel_pending_questions("session interrupted by user")

        await managed.client.interrupt()

        # If the consumer task is still alive, cancel it. This handles cases where
        # the CLI hangs (e.g. malformed input) and never sends a ResultMessage in
        # response to the interrupt signal.
        if managed.consumer_task and not managed.consumer_task.done():
            managed.consumer_task.cancel()

        return managed.status

    async def _consume_messages(self, managed: ManagedSession) -> None:
        """Consume messages from client and distribute to subscribers."""
        try:
            async for message in managed.client.receive_response():
                msg_dict = self._message_to_dict(message)
                if not isinstance(msg_dict, dict):
                    continue

                if self._is_duplicate_user_echo(managed, msg_dict):
                    await self._on_sdk_session_id_received(managed, message, msg_dict)
                    continue

                self._handle_special_message(managed, msg_dict)
                managed.add_message(msg_dict)
                await self._on_sdk_session_id_received(managed, message, msg_dict)

                if msg_dict.get("type") != "result":
                    continue

                await self._finalize_turn(managed, msg_dict)

        except asyncio.CancelledError:
            await self._mark_session_terminal(managed, "interrupted", "session interrupted")
            raise
        except Exception:
            logger.exception("會話消費迴圈異常")
            await self._mark_session_terminal(managed, "error", "session error")
            raise

    def _handle_special_message(self, managed: ManagedSession, msg_dict: dict[str, Any]) -> None:
        """Handle compact_boundary and result messages before broadcast."""
        if msg_dict.get("type") == "system" and msg_dict.get("subtype") == "compact_boundary":
            self._prune_transient_buffer(managed)

        if msg_dict.get("type") == "result":
            msg_dict["session_status"] = self._resolve_result_status(
                msg_dict,
                interrupt_requested=managed.interrupt_requested,
            )

    async def _finalize_turn(self, managed: ManagedSession, result_msg: dict[str, Any]) -> None:
        """Settle session state after a result message completes a turn."""
        managed.pending_user_echoes.clear()
        managed.cancel_pending_questions("session completed")
        explicit = str(result_msg.get("session_status") or "").strip()
        final_status: SessionStatus = (
            explicit  # type: ignore[assignment]
            if explicit in {"idle", "running", "completed", "error", "interrupted"}
            else self._resolve_result_status(
                result_msg,
                interrupt_requested=managed.interrupt_requested,
            )
        )
        managed.status = final_status
        managed.last_activity = time.monotonic()
        await self.meta_store.update_status(managed.session_id, final_status)
        managed.interrupt_requested = False
        self._prune_transient_buffer(managed)
        if final_status != "running":
            self._schedule_cleanup(managed.session_id)

    async def _mark_session_terminal(self, managed: ManagedSession, status: SessionStatus, reason: str) -> None:
        """Set terminal status on abnormal consumer exit."""
        managed.pending_user_echoes.clear()
        managed.cancel_pending_questions(reason)
        managed.status = status
        managed.last_activity = time.monotonic()
        await self.meta_store.update_status(managed.session_id, status)
        managed.interrupt_requested = False
        self._prune_transient_buffer(managed)

        # For interrupted sessions, broadcast a synthetic interrupt echo so the
        # SSE projector generates an interrupt_notice turn.  This keeps the live
        # path consistent with the historical path where the SDK transcript
        # contains the CLI-injected interrupt echo that the turn_grouper converts.
        # The consumer task is already cancelled at this point so the SDK's own
        # echo will never arrive through the normal message pipeline.
        if status == "interrupted":
            managed._broadcast_to_subscribers(
                {
                    "type": "user",
                    "content": "[Request interrupted by user]",
                    "uuid": f"interrupt-echo-{uuid4().hex}",
                    "timestamp": _utc_now_iso(),
                }
            )

        # Broadcast terminal status so SSE subscribers unblock immediately
        # instead of waiting for the heartbeat timeout.
        managed._broadcast_to_subscribers(
            {
                "type": "runtime_status",
                "status": status,
                "reason": reason,
            }
        )
        self._schedule_cleanup(managed.session_id)

    def _schedule_cleanup(self, session_id: str) -> None:
        """為非 running 會話排程延遲清理，延遲從配置讀取。"""
        managed = self.sessions.get(session_id)
        if managed is None:
            return
        # 取消舊的 cleanup task
        if managed._cleanup_task and not managed._cleanup_task.done():
            managed._cleanup_task.cancel()

        async def _do_cleanup() -> None:
            delay = await self._get_cleanup_delay()
            await asyncio.sleep(delay)
            m = self.sessions.get(session_id)
            if m is None:
                return
            # 會話已恢復活躍 → 跳過
            if m.status == "running":
                return
            logger.info("清理會話 session_id=%s status=%s", session_id, m.status)
            # 清除自身引用，避免 _disconnect_session 嘗試 cancel/gather 當前任務
            m._cleanup_task = None
            try:
                await self._disconnect_session(session_id, reason="cleanup timer")
            except Exception:
                logger.warning("清理會話失敗 session_id=%s", session_id, exc_info=True)

        managed._cleanup_task = asyncio.create_task(_do_cleanup())

    async def close_session(self, session_id: str, *, reason: str = "session closed") -> None:
        """Public close entry for explicit session teardown paths."""
        await self._disconnect_session(
            session_id,
            reason=reason,
            interrupt_running=True,
        )

    async def _disconnect_session(
        self,
        session_id: str,
        *,
        reason: str = "session closed",
        interrupt_running: bool = False,
    ) -> None:
        """安全斷開會話，確認子程序退出後再釋放槽位。"""
        if session_id in self._disconnecting:
            return
        managed = self.sessions.get(session_id)
        if managed is None:
            return
        self._disconnecting.add(session_id)
        try:
            await self._disconnect_session_inner(
                session_id,
                managed,
                reason=reason,
                interrupt_running=interrupt_running,
            )
        finally:
            self._disconnecting.discard(session_id)

    async def _disconnect_session_inner(
        self,
        session_id: str,
        managed: ManagedSession,
        *,
        reason: str,
        interrupt_running: bool,
    ) -> None:
        managed.cancel_pending_questions(reason)
        await proc.cancel_task(managed._cleanup_task)

        if interrupt_running and managed.status == "running":
            managed.pending_user_echoes.clear()
            managed.interrupt_requested = True
            try:
                await asyncio.wait_for(
                    managed.client.interrupt(),
                    timeout=self._INTERRUPT_TIMEOUT,
                )
            except TimeoutError:
                logger.warning("中斷會話超時 session_id=%s", session_id)
            except Exception:
                logger.warning("中斷會話失敗 session_id=%s", session_id, exc_info=True)

            managed.status = "interrupted"
            try:
                await self.meta_store.update_status(session_id, "interrupted")
            except Exception:
                logger.warning(
                    "更新會話中斷狀態失敗 session_id=%s",
                    session_id,
                    exc_info=True,
                )

        await proc.cancel_task(managed.consumer_task)
        await proc.cancel_task(managed._cleanup_task)

        process = proc.get_client_process(managed.client)
        pid = proc.process_pid(process)
        logger.info(
            "開始斷開會話 session_id=%s status=%s pid=%s reason=%s",
            session_id,
            managed.status,
            pid,
            reason,
        )

        disconnect_task = asyncio.create_task(managed.client.disconnect())
        disconnect_error: BaseException | None = None
        try:
            await asyncio.wait_for(disconnect_task, timeout=self._DISCONNECT_TIMEOUT)
        except TimeoutError as exc:
            disconnect_error = exc
            disconnect_task.cancel()
            await asyncio.gather(disconnect_task, return_exceptions=True)
        except Exception as exc:
            disconnect_error = exc

        closed = False
        if disconnect_error is None:
            closed = process is None or proc.process_returncode(process) is not None
            if not closed:
                logger.warning(
                    "disconnect 返回後 Claude 子程序仍存活 session_id=%s pid=%s",
                    session_id,
                    pid,
                )
        else:
            logger.warning(
                "優雅斷開會話失敗 session_id=%s pid=%s reason=%s error=%s",
                session_id,
                pid,
                reason,
                disconnect_error,
            )

        if not closed:
            closed = await proc.force_close_client_process(
                session_id,
                process,
                pid=pid,
                cause="disconnect_timeout"
                if isinstance(disconnect_error, asyncio.TimeoutError)
                else ("disconnect_error" if disconnect_error is not None else "process_still_running"),
                terminate_wait_timeout=self._TERMINATE_WAIT_TIMEOUT,
                kill_wait_timeout=self._KILL_WAIT_TIMEOUT,
            )

        if not closed:
            raise RuntimeError(f"failed to close Claude subprocess for session {session_id}") from disconnect_error

        managed.clear_buffer()
        self.sessions.pop(session_id, None)
        self._connect_locks.pop(session_id, None)
        logger.info(
            "會話已斷開 session_id=%s pid=%s returncode=%s",
            session_id,
            pid,
            proc.process_returncode(process),
        )

    async def _get_cleanup_delay(self) -> int:
        """返回會話清理延遲秒數，預設 300（5 分鐘）。"""
        try:
            async with async_session_factory() as session:
                svc = ConfigService(session)
                val = await svc.get_setting("agent_session_cleanup_delay_seconds", "300")
            return max(int(val), 10)
        except Exception:
            logger.warning("讀取 cleanup delay 配置失敗，使用預設值", exc_info=True)
            return 300

    async def _get_max_concurrent(self) -> int:
        """返回最大併發會話數，預設 5。"""
        try:
            async with async_session_factory() as session:
                svc = ConfigService(session)
                val = await svc.get_setting("agent_max_concurrent_sessions", "5")
            return max(int(val), 1)
        except Exception:
            logger.warning("讀取 max_concurrent 配置失敗，使用預設值", exc_info=True)
            return 5

    async def _ensure_capacity(self) -> None:
        """確保有空餘併發槽位，必要時淘汰最久未活躍的非 running 會話。"""
        max_concurrent = await self._get_max_concurrent()
        active = [s for s in self.sessions.values() if s.client is not None and s.session_id not in self._disconnecting]

        if len(active) < max_concurrent:
            return

        # 可淘汰的會話：非 running 狀態（idle / completed / error / interrupted）
        evictable = sorted(
            [s for s in active if s.status != "running"],
            key=lambda s: s.last_activity or 0,
        )

        if evictable:
            victim = evictable[0]
            logger.info(
                "併發上限，淘汰 session_id=%s (status=%s)",
                victim.session_id,
                victim.status,
            )
            try:
                await self._disconnect_session(
                    victim.session_id,
                    reason="capacity eviction",
                )
            except Exception as exc:
                logger.error(
                    "淘汰會話失敗，無法釋放併發槽位 session_id=%s",
                    victim.session_id,
                    exc_info=True,
                )
                raise SessionCapacityError("有尚未關閉的閒置會話，目前無法釋放並發槽位，請稍後再試") from exc
            return

        # 所有會話都在 running → 拒絕
        raise SessionCapacityError(f"目前有 {len(active)} 個正在進行的會話，已達最大上限，請稍後再試")

    _PATROL_INTERVAL = 300  # 5 分鐘

    async def _patrol_once(self) -> None:
        """單次巡檢：清理所有超時的非 running 會話。"""
        cleanup_delay = await self._get_cleanup_delay()
        now = time.monotonic()
        for sid, managed in list(self.sessions.items()):
            if managed.status == "running" or sid in self._disconnecting:
                continue
            activity_age = now - (managed.last_activity or 0)
            if activity_age > cleanup_delay * 2:
                logger.info("巡檢兜底清理會話 session_id=%s status=%s", sid, managed.status)
                try:
                    await self._disconnect_session(sid, reason="patrol cleanup")
                except Exception:
                    logger.warning(
                        "巡檢兜底清理失敗 session_id=%s",
                        sid,
                        exc_info=True,
                    )

    async def _patrol_loop(self) -> None:
        """後臺定期巡檢迴圈。"""
        while True:
            await asyncio.sleep(self._PATROL_INTERVAL)
            try:
                await self._patrol_once()
            except Exception:
                logger.warning("巡檢迴圈異常", exc_info=True)

    def start_patrol(self) -> None:
        """啟動巡檢後臺任務（應在應用 startup 時呼叫）。"""
        self._patrol_task = asyncio.create_task(self._patrol_loop())

    @staticmethod
    def _resolve_result_status(
        result_message: dict[str, Any],
        interrupt_requested: bool = False,
    ) -> SessionStatus:
        """Map SDK result subtype/is_error to runtime session status."""
        subtype = str(result_message.get("subtype") or "").strip().lower()
        is_error = bool(result_message.get("is_error"))
        if interrupt_requested:
            if subtype in {"interrupted", "interrupt"}:
                return "interrupted"
            if is_error or subtype.startswith("error"):
                return "interrupted"
        if is_error or subtype.startswith("error"):
            return "error"
        return "completed"

    # Base directory where the SDK stores per-project session data.
    _CLAUDE_PROJECTS_DIR: Path = Path.home() / ".claude" / "projects"

    @staticmethod
    def _encode_sdk_project_path(project_cwd: Path) -> str:
        return session_hooks.encode_sdk_project_path(project_cwd)

    def _is_path_allowed(
        self,
        file_path: str,
        tool_name: str,
        project_cwd: Path,
    ) -> tuple[bool, str | None]:
        return session_hooks.is_path_allowed(
            file_path,
            tool_name,
            project_cwd,
            project_root=self.project_root,
            write_tools=self._WRITE_TOOLS,
            writable_extensions=self._WRITABLE_EXTENSIONS,
            sdk_projects_dir=self._CLAUDE_PROJECTS_DIR,
        )

    async def _handle_ask_user_question(
        self,
        managed: Optional["ManagedSession"],
        tool_name: str,
        input_data: dict[str, Any],
    ) -> Any:
        return await session_hooks.handle_ask_user_question(
            managed,
            tool_name,
            input_data,
            permission_allow_cls=PermissionResultAllow,
            permission_deny_cls=PermissionResultDeny,
        )

    async def _build_can_use_tool_callback(
        self,
        session_id: str,
        managed_ref: list[Optional["ManagedSession"]] | None = None,
    ):
        return session_hooks.build_can_use_tool_callback(
            session_id=session_id,
            sessions=self.sessions,
            managed_ref=managed_ref,
            handle_ask_user_question_fn=self._handle_ask_user_question,
            permission_allow_cls=PermissionResultAllow,
            permission_deny_cls=PermissionResultDeny,
            relative_skills_prefix=agent_profile.RELATIVE_SKILLS_PREFIX,
        )

    def _message_to_dict(self, message: Any) -> dict[str, Any]:
        """Convert SDK message to dict for JSON serialization."""
        msg_dict = self._serialize_value(message)

        # Infer and add message type if not present
        if isinstance(msg_dict, dict) and "type" not in msg_dict:
            msg_type = self._infer_message_type(message)
            if msg_type:
                msg_dict["type"] = msg_type

        # Inject precise subtype for typed task messages
        if isinstance(msg_dict, dict):
            class_name = type(message).__name__
            subtype = self._TASK_MESSAGE_SUBTYPES.get(class_name)
            if subtype:
                msg_dict["subtype"] = subtype

        return msg_dict

    @staticmethod
    def _build_user_echo_message(
        text: str,
        content_blocks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Build a synthetic user message for real-time UI echo.

        When content_blocks is provided (e.g. image + text blocks), the echo
        content is a list of blocks so the UI can render image thumbnails in
        the bubble.  If no blocks are provided, content is the plain text string.
        """
        content: Any = content_blocks if content_blocks is not None else text
        return {
            "type": "user",
            "content": content,
            "uuid": f"local-user-{uuid4().hex}",
            "timestamp": _utc_now_iso(),
            "local_echo": True,
        }

    @staticmethod
    def _prune_transient_buffer(managed: ManagedSession) -> None:
        """Drop stale messages that should not leak into next round snapshots.

        Removes:
        - stream_event / runtime_status: transient streaming artifacts
        - user / assistant / result: already persisted in SDK transcript;
          keeping them causes duplicate turns because buffer messages lack
          the uuid that transcript messages carry, so _merge_raw_messages
          cannot deduplicate them.
        """
        if not managed.message_buffer:
            return
        managed.message_buffer = [
            message
            for message in managed.message_buffer
            if message.get("type")
            not in {
                "stream_event",
                "runtime_status",
                "user",
                "assistant",
                "result",
            }
        ]

    @staticmethod
    def _build_runtime_status_message(
        status: SessionStatus,
        session_id: str,
    ) -> dict[str, Any]:
        """Build runtime-only status message for SSE wake-up."""
        return {
            "type": "runtime_status",
            "status": status,
            "subtype": status,
            "stop_reason": None,
            "is_error": status == "error",
            "session_id": session_id,
            "uuid": f"runtime-status-{uuid4().hex}",
            "timestamp": _utc_now_iso(),
        }

    _extract_plain_user_content = staticmethod(extract_plain_user_content)

    def _is_duplicate_user_echo(
        self,
        managed: ManagedSession,
        message: dict[str, Any],
    ) -> bool:
        """Skip SDK-replayed user message if it matches local echo queue."""
        if not managed.pending_user_echoes:
            return False
        incoming = self._extract_plain_user_content(message)
        expected = managed.pending_user_echoes[0].strip()

        # Image-only sentinel: the SDK parser drops image blocks, so the
        # replayed UserMessage arrives with empty content (incoming is None).
        if not incoming:
            if message.get("type") != "user" or expected != self._IMAGE_ONLY_SENTINEL:
                return False
            managed.pending_user_echoes.pop(0)
            return True

        if incoming != expected:
            return False
        managed.pending_user_echoes.pop(0)
        return True

    async def _on_sdk_session_id_received(
        self,
        managed: ManagedSession,
        message: Any,
        msg_dict: dict[str, Any],
    ) -> None:
        """Handle sdk_session_id from stream. For new sessions: create DB record + signal event."""
        sdk_id = self._extract_sdk_session_id(message, msg_dict)
        if not sdk_id:
            return
        if managed.resolved_sdk_id is not None:
            return  # Already registered

        managed.resolved_sdk_id = sdk_id

        # Only create DB record for new sessions (no existing meta)
        if not managed.sdk_id_event.is_set():
            # Run DB create and SDK tag in parallel (tag is independent file I/O)
            tag_coro = None
            if tag_session is not None:

                async def _tag() -> None:
                    try:
                        await asyncio.to_thread(tag_session, sdk_id, f"project:{managed.project_name}")
                    except Exception:
                        logger.warning("tag_session failed for %s", sdk_id, exc_info=True)

                tag_coro = _tag()
            await asyncio.gather(
                self.meta_store.create(managed.project_name, sdk_id),
                *([] if tag_coro is None else [tag_coro]),
            )
            await self.meta_store.update_status(sdk_id, "running")
            # Key swap: replace temp_id with real sdk_id in sessions dict
            # BEFORE signaling the event. This prevents _finalize_turn from
            # using the stale temp_id if it runs before send_new_session
            # completes its own key swap.
            old_id = managed.session_id
            if old_id != sdk_id and old_id in self.sessions:
                del self.sessions[old_id]
                managed.session_id = sdk_id
                self.sessions[sdk_id] = managed
            managed.sdk_id_event.set()

    @staticmethod
    def _extract_sdk_session_id(message: Any, msg_dict: dict[str, Any]) -> str | None:
        """Extract SDK session id from either serialized payload or raw object."""
        sdk_id = None
        if isinstance(msg_dict, dict):
            sdk_id = msg_dict.get("session_id") or msg_dict.get("sessionId")
        if sdk_id:
            return str(sdk_id)
        raw_sdk_id = getattr(message, "session_id", None) or getattr(message, "sessionId", None)
        if raw_sdk_id:
            return str(raw_sdk_id)
        return None

    def _infer_message_type(self, message: Any) -> str | None:
        """Infer message type from SDK message class name."""
        class_name = type(message).__name__
        return self._MESSAGE_TYPE_MAP.get(class_name)

    def _serialize_value(self, value: Any) -> Any:
        """Recursively serialize a value to JSON-safe types."""
        if value is None or isinstance(value, (bool, int, float, str)):
            return value

        if isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}

        if isinstance(value, (list, tuple)):
            return [self._serialize_value(item) for item in value]

        # Pydantic models
        if hasattr(value, "model_dump"):
            dumped = value.model_dump()
            return self._serialize_value(dumped)

        # Dataclasses or objects with __dict__
        if hasattr(value, "__dict__"):
            return {k: self._serialize_value(v) for k, v in value.__dict__.items() if not k.startswith("_")}

        # Fallback: convert to string
        return str(value)

    async def get_message_buffer_snapshot(self, session_id: str) -> list[dict[str, Any]]:
        """Get current message buffer without creating a new SDK connection."""
        managed = self.sessions.get(session_id)
        if not managed:
            return []
        return list(managed.message_buffer)

    def get_buffered_messages(self, session_id: str) -> list[dict[str, Any]]:
        """Sync helper for consumers that only need in-memory buffer state."""
        managed = self.sessions.get(session_id)
        if not managed:
            return []
        return list(managed.message_buffer)

    async def get_pending_questions_snapshot(self, session_id: str) -> list[dict[str, Any]]:
        """Get unresolved AskUserQuestion payloads for reconnect."""
        managed = self.sessions.get(session_id)
        if not managed:
            return []
        return managed.get_pending_question_payloads()

    async def answer_user_question(
        self,
        session_id: str,
        question_id: str,
        answers: dict[str, str],
    ) -> None:
        """Resolve AskUserQuestion answers for a running session."""
        managed = self.sessions.get(session_id)
        if managed is None:
            raise ValueError("會話未在執行中，或目前沒有待回答的問題")
        if managed.status != "running":
            raise ValueError("會話未在執行中，或目前沒有待回答的問題")
        if not managed.resolve_pending_question(question_id, answers):
            raise ValueError("找不到待回答的問題")

    async def subscribe(self, session_id: str, replay_buffer: bool = True) -> asyncio.Queue:
        """Subscribe to session messages. Returns queue for SSE."""
        managed = await self.get_or_connect(session_id)
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)

        if replay_buffer:
            # Replay buffered messages
            for msg in managed.message_buffer:
                try:
                    queue.put_nowait(msg)
                except asyncio.QueueFull:
                    break

        managed.subscribers.add(queue)
        return queue

    async def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        """Unsubscribe from session messages."""
        if session_id in self.sessions:
            self.sessions[session_id].subscribers.discard(queue)

    async def get_status(self, session_id: str) -> SessionStatus | None:
        """Get session status."""
        if session_id in self.sessions:
            return self.sessions[session_id].status
        meta = await self.meta_store.get(session_id)
        return meta.status if meta else None

    async def shutdown_gracefully(self, timeout: float = 30.0) -> None:
        """Gracefully shutdown all sessions."""
        # 取消巡檢任務
        patrol = getattr(self, "_patrol_task", None)
        if patrol and not patrol.done():
            patrol.cancel()

        for session_id in list(self.sessions.keys()):
            managed = self.sessions.get(session_id)
            if managed is None:
                continue
            if managed.status == "running":
                # Wait for current turn
                if managed.consumer_task and not managed.consumer_task.done():
                    try:
                        await asyncio.wait_for(managed.consumer_task, timeout=timeout)
                    except TimeoutError:
                        try:
                            await managed.client.interrupt()
                        except Exception:
                            logger.warning(
                                "優雅關閉時中斷會話失敗 session_id=%s",
                                session_id,
                                exc_info=True,
                            )
                        managed.consumer_task.cancel()

                managed.status = "interrupted"
                await self.meta_store.update_status(session_id, "interrupted")

            try:
                await self._disconnect_session(
                    session_id,
                    reason="session shutdown",
                )
            except Exception:
                logger.warning(
                    "優雅關閉會話失敗 session_id=%s",
                    session_id,
                    exc_info=True,
                )
