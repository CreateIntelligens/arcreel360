"""助手工具的白名单沙盒 + 文件 IO 工具。

设计目标：
- 任何由 LLM 触发的文件读写都必须经 ``ToolSandbox.validate_path`` 校验。
- 校验先把请求路径解析为绝对路径（含符号链接），再对照项目根 + 白名单子目录。
- 工具函数（``fs_read`` / ``fs_write`` / ``fs_list``）返回结构化错误而非抛异常，
  让上层 provider 把 deny 结果以 ``functionResponse`` 形式喂回模型。

实现遵循 ``openspec/changes/add-gemini-full-runtime/specs/assistant-tool-sandbox/``。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# 单文件读取上限：1 MiB
DEFAULT_MAX_READ_BYTES = 1 * 1024 * 1024
# 单文件写入上限：10 MiB
MAX_WRITE_BYTES = 10 * 1024 * 1024

# 白名单：允许在项目根目录下访问的子目录
ALLOWED_SUBDIRS: frozenset[str] = frozenset(
    {
        "source",
        "scripts",
        "characters",
        "clues",
        "storyboards",
        "videos",
        "drafts",
        "output",
    }
)
# 白名单：允许在项目根目录下访问的具体文件
ALLOWED_FILES: frozenset[str] = frozenset({"project.json"})


class SandboxViolationError(Exception):
    """沙盒校验失敗时抛出。

    工具入口应捕获并转换为结构化错误返回模型，避免向 LLM 暴露异常 traceback。
    """

    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code = code
        self.reason = reason


@dataclass(frozen=True)
class ToolSandbox:
    """单個 session 的沙盒上下文。

    Attributes:
        project_root: 所有项目所在的根目录（如 ``/app/projects``）。
        project_name: 当前 session 绑定的项目名（白名单第一段）。
    """

    project_root: Path
    project_name: str

    @property
    def allowed_root(self) -> Path:
        """该 sandbox 实际允许访问的根目录绝对路径。"""
        return (self.project_root / self.project_name).resolve(strict=False)

    def validate_path(self, req_path: str, *, must_be_dir: bool = False) -> Path:
        """把 LLM 请求的相对路径校验并转换为安全的绝对路径。

        步骤：
        1. 拒绝绝对路径（``/etc/passwd`` 这类）。
        2. 拼接到项目根并 ``resolve``，让符号链接 + ``..`` 都展开为真实绝对路径。
        3. 校验展开结果落在 ``allowed_root`` 之下。
        4. 校验路径第一段命中白名单子目录或文件。
        """
        if not req_path or req_path == ".":
            raise SandboxViolationError("invalid_path", "path must not be empty")
        candidate = Path(req_path)
        if candidate.is_absolute():
            raise SandboxViolationError(
                "absolute_path_forbidden",
                "absolute paths are not allowed; use a path relative to the project root",
            )

        joined = (self.project_root / self.project_name / candidate).resolve(strict=False)
        allowed_root = self.allowed_root
        if joined != allowed_root and not joined.is_relative_to(allowed_root):
            raise SandboxViolationError(
                "sandbox_violation",
                "path outside project root",
            )

        # 取项目根之下的相对路径，第一段必须命中白名单
        try:
            rel = joined.relative_to(allowed_root)
        except ValueError:
            raise SandboxViolationError("sandbox_violation", "path outside project root") from None

        parts = rel.parts
        if not parts:
            # 直接指向项目根目录本身（例如 fs_list("")）
            raise SandboxViolationError("invalid_path", "must target a whitelisted subpath")

        first = parts[0]
        if first in ALLOWED_FILES:
            # 整路径必须正好等于白名单文件（不能有更深的子段）
            if len(parts) != 1:
                raise SandboxViolationError(
                    "not_in_whitelist",
                    "whitelist file does not allow nested children",
                )
            if must_be_dir:
                raise SandboxViolationError(
                    "not_a_directory",
                    "whitelisted entry is a single file, cannot be listed",
                )
        elif first not in ALLOWED_SUBDIRS:
            raise SandboxViolationError(
                "not_in_whitelist",
                f"first path segment {first!r} is not in the whitelist",
            )

        return joined


# ---------------------------------------------------------------------------
# 工具函数：每個都返回结构化 dict，供 functionResponse 直接序列化
# ---------------------------------------------------------------------------


def fs_read(
    sandbox: ToolSandbox,
    path: str,
    max_bytes: int = DEFAULT_MAX_READ_BYTES,
) -> dict[str, Any]:
    """读取文本文件，超过 ``max_bytes`` 时截断。

    返回:
        ``{"content": str, "bytes_read": int, "truncated": bool}`` 或 ``{"error": ...}``
    """
    try:
        target = sandbox.validate_path(path)
    except SandboxViolationError as exc:
        return {"error": exc.code, "reason": exc.reason}

    if not target.exists():
        return {"error": "not_found"}
    if not target.is_file():
        return {"error": "not_a_file"}

    try:
        raw = target.read_bytes()
    except OSError as exc:
        return {"error": "io_error", "reason": str(exc)}

    truncated = False
    if len(raw) > max_bytes:
        raw = raw[:max_bytes]
        truncated = True

    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        return {"error": "binary_file"}

    return {
        "content": content,
        "bytes_read": len(raw),
        "truncated": truncated,
    }


def fs_write(
    sandbox: ToolSandbox,
    path: str,
    content: str,
    mode: str = "overwrite",
) -> dict[str, Any]:
    """写入文本文件。

    Args:
        mode: ``"overwrite"``（默认）或 ``"create"``。后者在文件已存在时拒绝。

    ``project.json`` 是结构化元数据，必须经专用工具（``update_overview`` /
    ``generate_characters`` / ``generate_clues`` / ``generate_scenes`` /
    ``split_episode`` 等）写入以保证 schema 正确；直接用 ``fs_write`` 覆写它
    会绕过校验、写坏字段（例如把世界观写到 ``world_view`` 而非 ``overview``），
    导致专案进度无法推进。因此此处硬性拒绝。
    """
    if mode not in {"overwrite", "create"}:
        return {"error": "invalid_mode", "reason": f"mode must be overwrite or create, got {mode!r}"}

    if Path(path).name == "project.json":
        return {
            "error": "use_dedicated_tool",
            "reason": (
                "不可用 fs_write 改 project.json。世界觀請用 update_overview / generate_overview；"
                "角色/線索/場景請用 generate_characters / generate_clues / generate_scenes 或對應 update_* 工具；"
                "分集請用 split_episode。這些工具會寫入正確的結構化欄位並推進專案進度。"
            ),
        }

    encoded = content.encode("utf-8")
    if len(encoded) > MAX_WRITE_BYTES:
        return {
            "error": "content_too_large",
            "limit": MAX_WRITE_BYTES,
        }

    try:
        target = sandbox.validate_path(path)
    except SandboxViolationError as exc:
        return {"error": exc.code, "reason": exc.reason}

    existed = target.exists()
    if mode == "create" and existed:
        return {"error": "already_exists"}

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(encoded)
    except OSError as exc:
        return {"error": "io_error", "reason": str(exc)}

    return {
        "bytes_written": len(encoded),
        "created": not existed,
    }


def fs_list(sandbox: ToolSandbox, path: str) -> dict[str, Any]:
    """列出目录下直接子项。隐藏文件（``.`` 开头）会被过滤掉。"""
    try:
        target = sandbox.validate_path(path, must_be_dir=True)
    except SandboxViolationError as exc:
        return {"error": exc.code, "reason": exc.reason}

    if not target.exists():
        return {"error": "not_found"}
    if not target.is_dir():
        return {"error": "not_a_directory"}

    entries: list[dict[str, Any]] = []
    try:
        for child in sorted(target.iterdir(), key=lambda p: p.name):
            if child.name.startswith("."):
                continue
            stat = child.stat()
            entries.append(
                {
                    "name": child.name,
                    "is_dir": child.is_dir(),
                    "size": stat.st_size,
                }
            )
    except OSError as exc:
        return {"error": "io_error", "reason": str(exc)}

    return {"entries": entries}


# ---------------------------------------------------------------------------
# fs_* 工具的 FunctionDeclaration（plain dict 形式，給 ADK BaseTool 包裝層使用）
#
# 這三個常量原本定義於 server/agent_runtime/gemini_full_runtime_provider.py，
# 隨 legacy provider 移除後搬到此處作為中性位置；ADK 適配層
# (adk_tool_adapters.py) 會將其轉換為 google.genai.types.FunctionDeclaration。
# ---------------------------------------------------------------------------

FS_READ_DECLARATION: dict[str, Any] = {
    "name": "fs_read",
    "description": "讀取專案內文字檔案。路徑相對於專案根目錄,且必須落在白名單子目錄(source/scripts/characters/clues/storyboards/videos/drafts/output/)或 project.json。",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "專案內相對路徑"},
            "max_bytes": {
                "type": "integer",
                "description": "最大讀取位元組數,預設 1 MiB",
            },
        },
        "required": ["path"],
    },
}

FS_WRITE_DECLARATION: dict[str, Any] = {
    "name": "fs_write",
    "description": (
        "寫入專案內文字檔案。僅允許白名單路徑,單檔上限 10 MiB。"
        "禁止用於 project.json——世界觀請用 update_overview,角色/線索/場景請用 "
        "generate_characters/generate_clues/generate_scenes,分集請用 split_episode。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "專案內相對路徑"},
            "content": {"type": "string", "description": "要寫入的 UTF-8 文字內容"},
            "mode": {
                "type": "string",
                "enum": ["overwrite", "create"],
                "description": "overwrite 會覆寫;create 在檔案已存在時拒絕",
            },
        },
        "required": ["path", "content"],
    },
}

FS_LIST_DECLARATION: dict[str, Any] = {
    "name": "fs_list",
    "description": "列出白名單目錄下的直接子項,不遞迴,並過濾隱藏檔案。",
    "parameters": {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "白名單目錄的相對路徑"}},
        "required": ["path"],
    },
}


# ---------------------------------------------------------------------------
# 共用 async FS handlers（簽名與 SkillHandler 對齊：(ctx, args) -> dict）
#
# `ctx` 須具備 `.sandbox` 屬性（型別為 ToolSandbox），即 `SkillCallContext`,
# 但此處用 `Any` 標註以避免與 `skill_function_declarations` 形成 import 循環。
# ADK / OpenAI adapter 都直接複用,避免 11 個工具的 handler 各寫一份。
# ---------------------------------------------------------------------------


async def fs_read_handler(ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
    return fs_read(
        ctx.sandbox,
        str(args.get("path") or ""),
        max_bytes=int(args.get("max_bytes") or 1024 * 1024),
    )


async def fs_write_handler(ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
    path = str(args.get("path") or "")
    result = fs_write(
        ctx.sandbox,
        path,
        str(args.get("content") or ""),
        mode=str(args.get("mode") or "overwrite"),
    )
    if "error" not in result:
        _sync_script_index_after_write(ctx, path, result)
    return result


def _sync_script_index_after_write(ctx: Any, path: str, result: dict[str, Any]) -> None:
    project_manager = getattr(ctx, "project_manager", None)
    project_name = getattr(ctx, "project_name", None)
    sandbox = getattr(ctx, "sandbox", None)
    if project_manager is None or not project_name or sandbox is None:
        return

    try:
        target = sandbox.validate_path(path)
        rel = target.relative_to(sandbox.allowed_root)
    except Exception:
        return

    if len(rel.parts) != 2 or rel.parts[0] != "scripts" or target.suffix.lower() != ".json":
        return

    try:
        script = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return
    if not isinstance(script, dict) or not isinstance(script.get("episode"), int):
        return

    try:
        project_manager.sync_episode_from_script(project_name, rel.name)
        result["episode_synced"] = True
    except Exception as exc:
        result["episode_sync_error"] = str(exc)


async def fs_list_handler(ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
    return fs_list(ctx.sandbox, str(args.get("path") or ""))
