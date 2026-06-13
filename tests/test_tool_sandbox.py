"""``server.agent_runtime.tool_sandbox`` 单元测试。

覆盖 ``openspec/changes/add-gemini-full-runtime/specs/assistant-tool-sandbox`` 中
所有 scenario：白名单合法访问、越界拒绝（绝对路径 / ``..`` / 符号链接）、
``fs_read`` 截断与二进制拒绝、``fs_write`` create 冲突与超限、``fs_list`` 隐藏文件过滤。
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from lib.project_manager import ProjectManager
from server.agent_runtime.tool_sandbox import (
    ALLOWED_SUBDIRS,
    MAX_WRITE_BYTES,
    SandboxViolationError,
    ToolSandbox,
    fs_list,
    fs_read,
    fs_write,
    fs_write_handler,
)


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """模拟 ``/app/projects`` 容器内根目录。"""
    return tmp_path


@pytest.fixture
def sandbox(project_root: Path) -> ToolSandbox:
    project_dir = project_root / "demo"
    for sub in ALLOWED_SUBDIRS:
        (project_dir / sub).mkdir(parents=True)
    (project_dir / "project.json").write_text("{}", encoding="utf-8")
    return ToolSandbox(project_root=project_root, project_name="demo")


# ---------------------------------------------------------------------------
# validate_path
# ---------------------------------------------------------------------------


def test_validate_path_accepts_whitelisted_subdir(sandbox: ToolSandbox) -> None:
    target = sandbox.validate_path("scripts/episode_1.json")
    assert target == sandbox.allowed_root / "scripts" / "episode_1.json"


def test_validate_path_accepts_project_json_file(sandbox: ToolSandbox) -> None:
    target = sandbox.validate_path("project.json")
    assert target.name == "project.json"


def test_validate_path_rejects_absolute(sandbox: ToolSandbox) -> None:
    with pytest.raises(SandboxViolationError) as exc:
        sandbox.validate_path("/etc/passwd")
    assert exc.value.code == "absolute_path_forbidden"


def test_validate_path_rejects_parent_traversal(sandbox: ToolSandbox) -> None:
    with pytest.raises(SandboxViolationError) as exc:
        sandbox.validate_path("../other-project/project.json")
    assert exc.value.code == "sandbox_violation"


def test_validate_path_rejects_non_whitelisted_subdir(sandbox: ToolSandbox) -> None:
    with pytest.raises(SandboxViolationError) as exc:
        sandbox.validate_path(".arcreel.db")
    assert exc.value.code == "not_in_whitelist"


def test_validate_path_rejects_nested_under_whitelist_file(sandbox: ToolSandbox) -> None:
    with pytest.raises(SandboxViolationError) as exc:
        sandbox.validate_path("project.json/foo")
    assert exc.value.code == "not_in_whitelist"


def test_validate_path_rejects_empty(sandbox: ToolSandbox) -> None:
    with pytest.raises(SandboxViolationError):
        sandbox.validate_path("")


def test_validate_path_must_be_dir_rejects_file(sandbox: ToolSandbox) -> None:
    with pytest.raises(SandboxViolationError) as exc:
        sandbox.validate_path("project.json", must_be_dir=True)
    assert exc.value.code == "not_a_directory"


@pytest.mark.skipif(os.name == "nt", reason="symlink semantics differ on Windows")
def test_validate_path_blocks_symlink_escape(project_root: Path, sandbox: ToolSandbox, tmp_path: Path) -> None:
    # Create a secret file outside any project, then symlink it inside source/
    secret = tmp_path / "external_secret"
    secret.write_text("oops", encoding="utf-8")

    link = sandbox.allowed_root / "source" / "link"
    link.symlink_to(secret)

    with pytest.raises(SandboxViolationError) as exc:
        sandbox.validate_path("source/link")
    assert exc.value.code == "sandbox_violation"


# ---------------------------------------------------------------------------
# fs_read
# ---------------------------------------------------------------------------


def test_fs_read_returns_content(sandbox: ToolSandbox) -> None:
    f = sandbox.allowed_root / "scripts" / "episode_1.json"
    f.write_text('{"hi": 1}', encoding="utf-8")

    result = fs_read(sandbox, "scripts/episode_1.json")
    assert result == {"content": '{"hi": 1}', "bytes_read": 9, "truncated": False}


def test_fs_read_truncates_oversize(sandbox: ToolSandbox) -> None:
    f = sandbox.allowed_root / "source" / "big.txt"
    payload = "a" * 5000
    f.write_text(payload, encoding="utf-8")

    result = fs_read(sandbox, "source/big.txt", max_bytes=1000)
    assert result["truncated"] is True
    assert result["bytes_read"] == 1000
    assert len(result["content"]) == 1000


def test_fs_read_rejects_binary(sandbox: ToolSandbox) -> None:
    f = sandbox.allowed_root / "source" / "blob.bin"
    f.write_bytes(b"\xff\xfe\x00\x01\x02")

    result = fs_read(sandbox, "source/blob.bin")
    assert result == {"error": "binary_file"}


def test_fs_read_returns_not_found(sandbox: ToolSandbox) -> None:
    result = fs_read(sandbox, "source/missing.txt")
    assert result == {"error": "not_found"}


def test_fs_read_returns_violation_on_escape(sandbox: ToolSandbox) -> None:
    result = fs_read(sandbox, "../escape.txt")
    assert result["error"] == "sandbox_violation"


# ---------------------------------------------------------------------------
# fs_write
# ---------------------------------------------------------------------------


def test_fs_write_creates_new_file(sandbox: ToolSandbox) -> None:
    result = fs_write(sandbox, "scripts/new.json", "hello")
    assert result == {"bytes_written": 5, "created": True}
    assert (sandbox.allowed_root / "scripts" / "new.json").read_text("utf-8") == "hello"


def test_fs_write_overwrites_existing(sandbox: ToolSandbox) -> None:
    target = sandbox.allowed_root / "scripts" / "x.txt"
    target.write_text("old", encoding="utf-8")

    result = fs_write(sandbox, "scripts/x.txt", "new")
    assert result == {"bytes_written": 3, "created": False}
    assert target.read_text("utf-8") == "new"


def test_fs_write_create_mode_rejects_existing(sandbox: ToolSandbox) -> None:
    target = sandbox.allowed_root / "scripts" / "x.txt"
    target.write_text("here", encoding="utf-8")

    result = fs_write(sandbox, "scripts/x.txt", "fresh", mode="create")
    assert result == {"error": "already_exists"}
    assert target.read_text("utf-8") == "here"


def test_fs_write_rejects_oversize(sandbox: ToolSandbox) -> None:
    payload = "x" * (MAX_WRITE_BYTES + 1)
    result = fs_write(sandbox, "scripts/big.txt", payload)
    assert result == {"error": "content_too_large", "limit": MAX_WRITE_BYTES}


def test_fs_write_rejects_invalid_mode(sandbox: ToolSandbox) -> None:
    result = fs_write(sandbox, "scripts/x.txt", "y", mode="append")
    assert result["error"] == "invalid_mode"


def test_fs_write_rejects_outside_path(sandbox: ToolSandbox) -> None:
    result = fs_write(sandbox, "/tmp/escape.txt", "x")
    assert result["error"] == "absolute_path_forbidden"


def test_fs_write_rejects_project_json(sandbox: ToolSandbox) -> None:
    """project.json 必須經專用工具寫入，fs_write 直接拒絕且不改動檔案。"""
    target = sandbox.allowed_root / "project.json"
    original = target.read_text(encoding="utf-8")

    result = fs_write(sandbox, "project.json", '{"world_view": {"summary": "x"}}')

    assert result["error"] == "use_dedicated_tool"
    assert "update_overview" in result["reason"]
    # 檔案內容必須原封不動
    assert target.read_text(encoding="utf-8") == original


def test_fs_write_creates_missing_parent(sandbox: ToolSandbox) -> None:
    result = fs_write(sandbox, "drafts/episode_2/scene_1.txt", "hi")
    assert result["bytes_written"] == 2
    assert (sandbox.allowed_root / "drafts" / "episode_2" / "scene_1.txt").exists()


@pytest.mark.asyncio
async def test_fs_write_handler_syncs_episode_index_for_script_json(tmp_path: Path) -> None:
    pm = ProjectManager(tmp_path / "projects")
    pm.create_project("demo")
    pm.create_project_metadata("demo", "Demo", "Anime", "narration")
    sandbox = ToolSandbox(project_root=tmp_path / "projects", project_name="demo")
    script = """
{
  "episode": 1,
  "title": "鏽鐵下的微光",
  "content_mode": "narration",
  "segments": []
}
""".strip()

    result = await fs_write_handler(
        SimpleNamespace(sandbox=sandbox, project_manager=pm, project_name="demo"),
        {"path": "scripts/episode_1.json", "content": script},
    )

    assert result["bytes_written"] == len(script.encode("utf-8"))
    project = pm.load_project("demo")
    assert project["episodes"] == [
        {
            "episode": 1,
            "order": 0,
            "title": "鏽鐵下的微光",
            "script_file": "scripts/episode_1.json",
        }
    ]


# ---------------------------------------------------------------------------
# fs_list
# ---------------------------------------------------------------------------


def test_fs_list_returns_entries(sandbox: ToolSandbox) -> None:
    src = sandbox.allowed_root / "source"
    (src / "a.txt").write_text("a", encoding="utf-8")
    (src / "b.txt").write_text("bb", encoding="utf-8")
    (src / "subdir").mkdir()

    result = fs_list(sandbox, "source")
    names = [e["name"] for e in result["entries"]]
    assert names == ["a.txt", "b.txt", "subdir"]
    assert any(e["is_dir"] for e in result["entries"])
    assert all("size" in e for e in result["entries"])


def test_fs_list_filters_hidden(sandbox: ToolSandbox) -> None:
    src = sandbox.allowed_root / "source"
    (src / ".hidden").write_text("h", encoding="utf-8")
    (src / "visible.txt").write_text("v", encoding="utf-8")

    result = fs_list(sandbox, "source")
    names = [e["name"] for e in result["entries"]]
    assert names == ["visible.txt"]


def test_fs_list_rejects_file_path(sandbox: ToolSandbox) -> None:
    result = fs_list(sandbox, "project.json")
    assert result["error"] == "not_a_directory"


def test_fs_list_rejects_outside_whitelist(sandbox: ToolSandbox) -> None:
    result = fs_list(sandbox, ".agent_data")
    assert result["error"] == "not_in_whitelist"


def test_fs_list_returns_not_found_for_missing(sandbox: ToolSandbox) -> None:
    # whitelisted subdir but not yet created in this fixture? The fixture creates all,
    # so manually remove one to simulate missing.
    (sandbox.allowed_root / "videos").rmdir()
    result = fs_list(sandbox, "videos")
    assert result == {"error": "not_found"}
